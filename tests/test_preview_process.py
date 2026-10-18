from __future__ import annotations

import importlib
import multiprocessing
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PIL import Image

from svgconverter import EmbedOptions, VectorizationDependencyError
from svgconverter.preview import (
    PreviewCancelled,
    PreviewDependencyError,
    PreviewError,
    PreviewResult,
)


def process_module():
    return importlib.import_module("svgconverter.preview_process")


def successful_worker(sender, request, directory):
    (directory / "partial.svg").write_text("child output", encoding="utf-8")
    sender.send(
        PreviewResult(
            request.input_path,
            request.mode,
            b"source",
            b"rendered",
            (3, 2),
            (3, 2),
            os.getpid(),
            120,
            90,
            False,
        )
    )
    sender.close()


def blocked_worker(sender, _request, directory):
    marker = directory / "starting"
    marker.write_text(str(os.getpid()), encoding="ascii")
    marker.replace(directory / "started")
    while True:
        time.sleep(1)


def abrupt_worker(_sender, _request, directory):
    (directory / "partial.svg").write_text("unfinished", encoding="utf-8")
    os._exit(7)


def failure_worker(sender, request, _directory):
    module = process_module()
    kind = "vectorize" if request.mode == "vectorize" else "renderer"
    sender.send(module._PreviewFailure(kind, "backend unavailable"))
    sender.close()


def record_directories(monkeypatch: pytest.MonkeyPatch, module) -> list[Path]:
    directories: list[Path] = []

    def create_directory(*args, **kwargs):
        temporary = TemporaryDirectory(*args, **kwargs)
        directories.append(Path(temporary.name))
        return temporary

    monkeypatch.setattr(module, "TemporaryDirectory", create_directory)
    return directories


def test_preview_pipeline_executes_in_a_child_and_removes_parent_owned_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = process_module()
    directories = record_directories(monkeypatch, module)
    monkeypatch.setattr(module, "_preview_worker", successful_worker)
    source = tmp_path / "source.png"

    result = module.create_preview(source)

    # A thread or direct call would return this process's PID and fail this contract.
    assert result.input_bytes != os.getpid()
    assert result.source_png == b"source"
    assert result.rendered_png == b"rendered"
    assert directories
    assert not directories[0].exists()
    assert not multiprocessing.active_children()


def test_cancelling_running_preview_terminates_child_before_directory_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = process_module()
    directories = record_directories(monkeypatch, module)
    monkeypatch.setattr(module, "_preview_worker", blocked_worker)
    child_pid: list[int] = []

    def should_cancel() -> bool:
        if directories and (directories[0] / "started").exists():
            child_pid.append(
                int((directories[0] / "started").read_text(encoding="ascii"))
            )
            return True
        return False

    with pytest.raises(PreviewCancelled):
        module.create_preview(tmp_path / "source.png", should_cancel=should_cancel)

    assert child_pid
    assert child_pid[0] != os.getpid()
    assert not directories[0].exists()
    assert all(child.pid != child_pid[0] for child in multiprocessing.active_children())


def test_abrupt_worker_exit_reports_failure_and_cleans_private_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = process_module()
    directories = record_directories(monkeypatch, module)
    monkeypatch.setattr(module, "_preview_worker", abrupt_worker)

    with pytest.raises(PreviewError, match="worker.*7"):
        module.create_preview(tmp_path / "source.png")

    assert not directories[0].exists()
    assert not multiprocessing.active_children()


@pytest.mark.parametrize("mode", ["embed", "vectorize"])
def test_process_errors_preserve_dependency_categories_for_gui_localization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    module = process_module()
    monkeypatch.setattr(module, "_preview_worker", failure_worker)

    with pytest.raises(PreviewError, match="backend unavailable") as caught:
        module.create_preview(tmp_path / "source.png", mode=mode)

    if mode == "embed":
        assert isinstance(caught.value, PreviewDependencyError)
    else:
        assert isinstance(caught.value.__cause__, VectorizationDependencyError)
    assert not multiprocessing.active_children()


@pytest.mark.parametrize("mode", ["embed", "vectorize"])
def test_real_spawned_preview_matches_synchronous_result_and_keeps_final_svg(
    tmp_path: Path, mode: str
) -> None:
    pytest.importorskip("resvg_py")
    if mode == "vectorize":
        pytest.importorskip("vtracer")
    module = process_module()
    source = tmp_path / "影像 空白.png"
    Image.new("RGB", (24, 16), "red").save(source)
    final = source.with_suffix(".svg")
    final.write_text("existing SVG", encoding="utf-8")
    options = {"embed_options": EmbedOptions(max_width=12)} if mode == "embed" else {}

    result = module.create_preview(source, mode=mode, **options)

    assert result.source_size == (24, 16)
    assert result.output_size == ((12, 8) if mode == "embed" else (24, 16))
    assert result.source_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert result.rendered_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert result.svg_bytes > 0
    assert final.read_text(encoding="utf-8") == "existing SVG"
    assert set(tmp_path.iterdir()) == {source, final}


@pytest.mark.parametrize("failure", [None, "renderer", "vectorize", "error"])
def test_worker_serializes_result_and_errors_over_a_real_pipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    module = process_module()
    request = module._PreviewRequest(
        tmp_path / "source.png", "embed", None, None, (10, 10)
    )
    expected = PreviewResult(
        request.input_path,
        "embed",
        b"source",
        b"rendered",
        (10, 10),
        (10, 10),
        10,
        20,
        10,
        False,
    )
    if failure is None:

        def pipeline(*_args, **_kwargs):
            return expected
    else:
        if failure == "renderer":
            error = PreviewDependencyError("missing renderer")
        elif failure == "vectorize":
            error = PreviewError("missing VTracer")
            error.__cause__ = VectorizationDependencyError("missing VTracer")
        else:
            error = PreviewError("bad image")

        def pipeline(*_args, **_kwargs):
            raise error

    monkeypatch.setattr(module, "_create_preview_in_directory", pipeline)
    receiver, sender = multiprocessing.get_context("spawn").Pipe(duplex=False)
    try:
        module._preview_worker(sender, request, tmp_path)
        message = receiver.recv()
        if failure is None:
            assert module._decode_result(message) == expected
        else:
            assert message.kind == failure
            with pytest.raises(PreviewError, match=str(error)):
                module._decode_result(message)
    finally:
        receiver.close()
        sender.close()


def test_preview_cancelled_before_start_does_not_spawn_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import Mock

    module = process_module()
    context = Mock()
    monkeypatch.setattr(module.multiprocessing, "get_context", context)

    with pytest.raises(PreviewCancelled):
        module.create_preview(tmp_path / "source.png", should_cancel=lambda: True)

    context.assert_not_called()


def test_process_start_failure_closes_resources_and_removes_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import Mock

    module = process_module()
    directories = record_directories(monkeypatch, module)
    receiver, sender = multiprocessing.get_context("spawn").Pipe(duplex=False)
    process = Mock()
    process.pid = None
    process.start.side_effect = OSError("process limit")
    context = Mock()
    context.Pipe.return_value = (receiver, sender)
    context.Process.return_value = process
    monkeypatch.setattr(module.multiprocessing, "get_context", lambda _method: context)

    with pytest.raises(
        PreviewError, match="Cannot start preview worker: process limit"
    ):
        module.create_preview(tmp_path / "source.png")

    assert receiver.closed
    assert sender.closed
    assert directories
    assert not directories[0].exists()
    process.close.assert_called_once()


def test_gui_preview_worker_uses_the_process_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from queue import Queue
    from threading import Event

    from svgconverter.gui import GuiConversionOptions, SVGConverterApp

    module = process_module()
    directories = record_directories(monkeypatch, module)
    monkeypatch.setattr(module, "_preview_worker", successful_worker)
    app = object.__new__(SVGConverterApp)
    app._events = Queue()
    app._cancel_event = Event()
    options = GuiConversionOptions("embed", "ignored", True, True, None, None)

    app._run_preview(str(tmp_path / "source.png"), options)

    kind, result = app._events.get_nowait()
    assert kind == "preview_done"
    assert result.input_bytes != os.getpid()
    assert not directories[0].exists()
