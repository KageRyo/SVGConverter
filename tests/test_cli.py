from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from svgconverter.cli import main


def create_image(path: Path, image_format: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (2, 2), color=(25, 50, 75))
    image.save(path, format=image_format)
    return path


def test_cli_converts_single_file_to_explicit_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    destination = tmp_path / "output.svg"

    exit_code = main([str(source), "--output", str(destination)])

    assert exit_code == 0
    assert destination.is_file()
    assert "Converted:" in capsys.readouterr().out


def test_cli_converts_directory_and_reports_a_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_directory = tmp_path / "images"
    source_directory.mkdir()
    create_image(source_directory / "good.png", "PNG")
    (source_directory / "bad.jpg").write_bytes(b"not an image")
    output_directory = tmp_path / "out"

    exit_code = main([str(source_directory), "--output-dir", str(output_directory)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert (output_directory / "good.svg").is_file()
    assert "Summary: 1 converted, 0 skipped, 1 failed" in captured.out


def test_cli_recursively_converts_directories_with_relative_output_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_directory = tmp_path / "images"
    create_image(source_directory / "top.png", "PNG")
    create_image(source_directory / "nested" / "top.png", "PNG")
    output_directory = tmp_path / "out"

    exit_code = main(
        [
            str(source_directory),
            "--output-dir",
            str(output_directory),
            "--recursive",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert (output_directory / "top.svg").is_file()
    assert (output_directory / "nested" / "top.svg").is_file()
    assert "Summary: 2 converted, 0 skipped, 0 failed" in captured.out


def test_cli_converts_multiple_files_to_an_output_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = create_image(tmp_path / "first.png", "PNG")
    second = create_image(tmp_path / "second.jpg", "JPEG")
    output_directory = tmp_path / "out"

    exit_code = main([str(first), str(second), "--output-dir", str(output_directory)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert (output_directory / "first.svg").is_file()
    assert (output_directory / "second.svg").is_file()
    assert "Summary: 2 converted, 0 skipped, 0 failed" in captured.out


def test_cli_summarizes_existing_outputs_as_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_directory = tmp_path / "images"
    create_image(source_directory / "sample.png", "PNG")
    output_directory = tmp_path / "out"
    output_directory.mkdir()
    (output_directory / "sample.svg").write_text("existing", encoding="utf-8")

    exit_code = main([str(source_directory), "--output-dir", str(output_directory)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Skipped:" in captured.out
    assert "Summary: 0 converted, 1 skipped, 0 failed" in captured.out


def test_cli_uses_nonzero_exit_code_for_invalid_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_status:
        main([str(tmp_path / "missing.png")])

    assert exit_status.value.code == 1
    assert "does not exist" in capsys.readouterr().err
