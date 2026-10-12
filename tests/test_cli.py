from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

import svgconverter.converter as converter_module
from svgconverter.cli import main


def create_image(path: Path, image_format: str, size: tuple[int, int] = (2, 2)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, color=(25, 50, 75))
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


def test_cli_reports_safe_publication_error_and_explicit_overwrite_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    destination = tmp_path / "result.svg"

    def unsupported_link(_staged: Path, _destination: Path) -> None:
        raise OSError("hard links are unsupported")

    monkeypatch.setattr(converter_module.os, "link", unsupported_link)
    arguments = [str(source), "--output", str(destination)]
    with pytest.raises(SystemExit) as error:
        main(arguments)

    message = capsys.readouterr().err
    assert error.value.code == 1
    assert "hard links are unsupported" in message
    assert (
        "Choose an output directory with hard-link or exclusive-rename support"
        in message
    )
    assert "--overwrite only if replacing existing output is acceptable" in message
    assert not destination.exists()
    assert not list(tmp_path.glob(".result-*.svg.tmp"))

    assert main([*arguments, "--overwrite"]) == 0
    assert destination.read_text(encoding="utf-8").endswith("</svg>\n")


@pytest.mark.parametrize("overwrite", [False, True])
def test_cli_single_file_output_directory_handles_existing_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], overwrite: bool
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    output_directory = tmp_path / "out"
    output_directory.mkdir()
    destination = output_directory / "sample.svg"
    destination.write_text("existing", encoding="utf-8")
    arguments = [str(source), "--output-dir", str(output_directory)]
    if overwrite:
        arguments.append("--overwrite")

    assert main(arguments) == 0

    captured = capsys.readouterr()
    if overwrite:
        assert "<svg" in destination.read_text(encoding="utf-8")
        assert "Summary: 1 converted, 0 skipped, 0 failed" in captured.out
    else:
        assert destination.read_text(encoding="utf-8") == "existing"
        assert "Summary: 0 converted, 1 skipped, 0 failed" in captured.out


def test_cli_converts_single_file_to_output_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG", (120, 60))
    output_directory = tmp_path / "out"

    assert (
        main([str(source), "--output-dir", str(output_directory), "--max-width", "30"])
        == 0
    )

    captured = capsys.readouterr()
    destination = output_directory / "sample.svg"
    assert 'width="30" height="15"' in destination.read_text(encoding="utf-8")
    assert not source.with_suffix(".svg").exists()
    assert "Summary: 1 converted, 0 skipped, 0 failed" in captured.out
    assert "Size summary:" in captured.out


def test_cli_single_file_output_directory_reports_conversion_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "bad.png"
    source.write_bytes(b"not an image")
    output_directory = tmp_path / "out"

    assert main([str(source), "--output-dir", str(output_directory)]) == 1

    assert not (output_directory / "bad.svg").exists()
    assert "Summary: 0 converted, 0 skipped, 1 failed" in capsys.readouterr().out


def test_cli_rejects_both_output_options(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    with pytest.raises(SystemExit) as exit_status:
        main(
            [
                str(source),
                "--output",
                str(tmp_path / "out.svg"),
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )
    assert exit_status.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_cli_single_file_output_directory_respects_allowed_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    allowed_root = tmp_path / "workspace"
    source = create_image(allowed_root / "sample.png", "PNG")
    output_directory = tmp_path / "outside"
    with pytest.raises(SystemExit) as exit_status:
        main(
            [
                str(source),
                "--output-dir",
                str(output_directory),
                "--allowed-root",
                str(allowed_root),
            ]
        )
    assert exit_status.value.code == 1
    assert "within allowed root" in capsys.readouterr().err
    assert not output_directory.exists()


@pytest.mark.parametrize("directory_input", [False, True])
def test_cli_reserves_explicit_output_for_one_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], directory_input: bool
) -> None:
    source = create_image(tmp_path / "images" / "first.png", "PNG")
    if directory_input:
        inputs = [str(source.parent)]
    else:
        second = create_image(tmp_path / "second.png", "PNG")
        inputs = [str(source), str(second)]

    with pytest.raises(SystemExit) as exit_status:
        main([*inputs, "--output", str(tmp_path / "out.svg")])

    assert exit_status.value.code == 2
    assert "single input file" in capsys.readouterr().err
    assert not (tmp_path / "out.svg").exists()


def test_cli_single_file_output_directory_rejects_a_file_destination(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    destination = tmp_path / "out"
    destination.write_text("existing", encoding="utf-8")

    with pytest.raises(SystemExit) as exit_status:
        main([str(source), "--output-dir", str(destination)])

    assert exit_status.value.code == 1
    assert "not a directory" in capsys.readouterr().err
    assert destination.read_text(encoding="utf-8") == "existing"


def test_cli_allowed_root_rejects_input_outside_boundary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    allowed_root = tmp_path / "workspace"
    allowed_root.mkdir()
    source = create_image(tmp_path / "outside.png", "PNG")

    with pytest.raises(SystemExit) as exit_status:
        main([str(source), "--allowed-root", str(allowed_root)])

    assert exit_status.value.code == 1
    assert "within allowed root" in capsys.readouterr().err


def test_cli_applies_embed_optimization_and_prints_size_metrics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG", (120, 60))
    destination = tmp_path / "output.svg"

    exit_code = main([str(source), "--output", str(destination), "--max-width", "30"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert 'width="30" height="15"' in destination.read_text(encoding="utf-8")
    assert "Sizes:" in captured.out
    assert "embedded raster" in captured.out


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


def test_cli_batch_summary_includes_size_metrics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_directory = tmp_path / "images"
    create_image(source_directory / "sample.png", "PNG")
    output_directory = tmp_path / "out"

    exit_code = main([str(source_directory), "--output-dir", str(output_directory)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Size summary:" in captured.out
    assert "embedded raster" in captured.out


def test_cli_uses_nonzero_exit_code_for_invalid_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_status:
        main([str(tmp_path / "missing.png")])

    assert exit_status.value.code == 1
    assert "does not exist" in capsys.readouterr().err
