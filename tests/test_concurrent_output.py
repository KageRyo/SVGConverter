from __future__ import annotations

import base64
import multiprocessing
import os
from multiprocessing.connection import Connection
from multiprocessing.synchronize import Barrier
from pathlib import Path

import pytest
from PIL import Image

import svgconverter.converter as converter_module
from svgconverter import ConversionError, OutputExistsError, convert_file, convert_paths


def _convert_in_process(
    source: Path, destination: Path, barrier: Barrier, result: Connection
) -> None:
    """Hold both writers after their existence checks, before publishing."""
    real_link = os.link
    real_replace = os.replace

    def synchronized_link(source_path: Path, destination_path: Path) -> None:
        barrier.wait(timeout=15)
        real_link(source_path, destination_path)

    def synchronized_replace(source_path: Path, destination_path: Path) -> None:
        barrier.wait(timeout=15)
        real_replace(source_path, destination_path)

    converter_module.os.link = synchronized_link
    converter_module.os.replace = synchronized_replace
    try:
        convert_file(source, destination)
    except OutputExistsError:
        result.send(("exists", source.name))
    except Exception as error:
        result.send((type(error).__name__, str(error)))
    else:
        result.send(("success", source.name))
    finally:
        result.close()


def test_concurrent_processes_preserve_the_winning_output(tmp_path: Path) -> None:
    sources = [tmp_path / "first.png", tmp_path / "second.png"]
    for source, color in zip(sources, ["red", "blue"], strict=True):
        Image.new("RGB", (3, 2), color).save(source)
    destination = tmp_path / "result.svg"
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    pipes = [context.Pipe(duplex=False) for _ in sources]
    processes = [
        context.Process(
            target=_convert_in_process, args=(source, destination, barrier, sender)
        )
        for source, (_, sender) in zip(sources, pipes, strict=True)
    ]
    try:
        for process in processes:
            process.start()
        for _, sender in pipes:
            sender.close()
        outcomes = []
        for receiver, _ in pipes:
            assert receiver.poll(30), "conversion process did not report its result"
            outcomes.append(receiver.recv())
        for process in processes:
            process.join(timeout=15)
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=15)
        for receiver, sender in pipes:
            receiver.close()
            sender.close()

    assert sorted(status for status, _ in outcomes) == ["exists", "success"]
    winner = next(name for status, name in outcomes if status == "success")
    document = destination.read_text(encoding="utf-8")
    assert document.endswith("</svg>\n")
    payload = document.split("base64,", 1)[1].split('"', 1)[0]
    assert base64.b64decode(payload) == (tmp_path / winner).read_bytes()
    assert not list(tmp_path.glob(".result-*.svg.tmp"))


def test_commit_collision_preserves_output_and_continues_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources = [tmp_path / "first.png", tmp_path / "second.png"]
    for source in sources:
        Image.new("RGB", (3, 2)).save(source)
    output_dir = tmp_path / "output"
    real_link = os.link

    def competing_link(staged: Path, destination: Path) -> None:
        if destination.name == "first.svg":
            destination.write_text("competing output", encoding="utf-8")
        real_link(staged, destination)

    monkeypatch.setattr(converter_module.os, "link", competing_link)
    result = convert_paths(sources, output_dir)

    assert result.success_count == 1
    assert result.failure_count == 1
    assert isinstance(result.failed[0].error, OutputExistsError)
    assert result.converted == (output_dir / "second.svg",)
    assert (output_dir / "first.svg").read_text(encoding="utf-8") == "competing output"
    assert not list(output_dir.glob("*.tmp"))


def test_unsupported_hard_links_fail_without_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (3, 2)).save(source)
    destination = tmp_path / "result.svg"

    def unsupported_link(_staged: Path, _destination: Path) -> None:
        raise OSError("hard links are unsupported")

    monkeypatch.setattr(converter_module.os, "link", unsupported_link)
    with pytest.raises(ConversionError, match="hard links are unsupported"):
        convert_file(source, destination)

    assert not destination.exists()
    assert not list(tmp_path.glob(".result-*.svg.tmp"))
