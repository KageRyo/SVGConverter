from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

import svgconverter.cli as cli_module
from svgconverter.cli import main
from svgconverter.models import BatchResult, ConversionMetrics


def create_image(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (3, 2), color=(25, 50, 75)).save(path)
    return path


def test_json_single_file_reports_unicode_paths_and_exact_sizes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = create_image(tmp_path / "影像 空白.png")
    output = tmp_path / "輸出 空白.svg"
    arguments = [str(source), "--output", str(output), "--json", "--overwrite"]

    assert main(arguments) == 0

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert captured.err == ""
    assert report == {
        "schema_version": 1,
        "inputs": [str(source)],
        "output": str(output),
        "output_dir": None,
        "mode": "embed",
        "totals": {"converted": 1, "skipped": 0, "failed": 0},
        "converted": [
            {
                "input_path": str(source),
                "output_path": str(output),
                "input_bytes": source.stat().st_size,
                "svg_bytes": output.stat().st_size,
                "embedded_raster_bytes": source.stat().st_size,
            }
        ],
        "skipped": [],
        "failed": [],
        "cancelled": False,
        "sizes": {
            "input_bytes": source.stat().st_size,
            "svg_bytes": output.stat().st_size,
            "embedded_raster_bytes": source.stat().st_size,
        },
        "error": None,
    }
    assert main(arguments) == 0
    assert capsys.readouterr().out == captured.out


def test_json_directory_continues_after_bad_image_and_reports_partial_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = tmp_path / "來源"
    source = create_image(directory / "有效.png")
    bad = directory / "broken.png"
    bad.write_bytes(b"not an image")
    output = tmp_path / "輸出"

    assert main([str(directory), "--output-dir", str(output), "--json"]) == 1

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert captured.err == ""
    assert report["totals"] == {"converted": 1, "skipped": 0, "failed": 1}
    assert report["output_dir"] == str(output)
    assert report["converted"][0]["input_path"] == str(source)
    assert report["converted"][0]["output_path"] == str(output / "有效.svg")
    assert report["failed"][0]["input_path"] == str(bad)
    assert report["failed"][0]["error_type"] == "ConversionError"
    assert report["failed"][0]["error"]
    assert report["sizes"]["input_bytes"] == source.stat().st_size
    assert report["error"] is None
    assert report["cancelled"] is False


def test_json_skip_reports_existing_destination_without_counting_sizes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = create_image(tmp_path / "source.png")
    output = tmp_path / "out"
    output.mkdir()
    destination = output / "source.svg"
    destination.write_text("existing", encoding="utf-8")

    assert main([str(source), "--output-dir", str(output), "--json"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["totals"] == {"converted": 0, "skipped": 1, "failed": 0}
    assert report["skipped"] == [
        {
            "input_path": str(source),
            "output_path": str(destination),
            "reason": "output already exists",
        }
    ]
    assert report["converted"] == []
    assert report["sizes"] == {
        "input_bytes": 0,
        "svg_bytes": 0,
        "embedded_raster_bytes": None,
    }
    assert destination.read_text(encoding="utf-8") == "existing"


@pytest.mark.parametrize("bad_count", [0, 2])
def test_json_empty_and_completely_failed_directories(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], bad_count: int
) -> None:
    directory = tmp_path / "images"
    directory.mkdir()
    (directory / "ignored.txt").write_text("not a supported image", encoding="utf-8")
    for index in range(bad_count):
        (directory / f"bad{index}.png").write_bytes(b"not an image")

    assert main([str(directory), "--json"]) == (1 if bad_count else 0)

    report = json.loads(capsys.readouterr().out)
    assert report["totals"] == {"converted": 0, "skipped": 0, "failed": bad_count}
    assert len(report["failed"]) == bad_count
    assert report["converted"] == []
    assert report["error"] is None


def test_json_multiple_missing_inputs_report_each_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sources = [tmp_path / "missing.png", tmp_path / "不存在.png"]

    assert main([*(str(source) for source in sources), "--json"]) == 1

    report = json.loads(capsys.readouterr().out)
    assert report["totals"] == {"converted": 0, "skipped": 0, "failed": 2}
    assert [failure["input_path"] for failure in report["failed"]] == [
        str(source) for source in sources
    ]
    assert all(
        failure["error_type"] == "InputPathError" for failure in report["failed"]
    )


def test_json_single_file_failure_is_a_structured_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "bad.png"
    source.write_bytes(b"not an image")

    assert main([str(source), "--json"]) == 1

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert captured.err == ""
    assert report["totals"] == {"converted": 0, "skipped": 0, "failed": 1}
    assert report["failed"][0]["input_path"] == str(source)
    assert report["error"] is None


@pytest.mark.parametrize("outside_boundary", [False, True])
def test_json_reports_operation_errors_without_fabricating_file_failures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], outside_boundary: bool
) -> None:
    if outside_boundary:
        source = create_image(tmp_path / "outside.png")
        boundary = tmp_path / "allowed"
        boundary.mkdir()
        arguments = [
            str(source),
            "--output-dir",
            str(boundary),
            "--allowed-root",
            str(boundary),
        ]
        expected_message = "within allowed root"
    else:
        arguments = [str(tmp_path / "missing-directory")]
        expected_message = "does not exist"

    assert main([*arguments, "--json"]) == 1

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert captured.err == ""
    assert report["error"]["error_type"] == "InputPathError"
    assert expected_message in report["error"]["error"]
    assert report["totals"] == {"converted": 0, "skipped": 0, "failed": 0}
    assert report["failed"] == []


@pytest.mark.parametrize(
    "invalid_option", [["--max-width", "bad"], ["--max-width", "0"], ["--unknown"]]
)
def test_json_argument_errors_use_stderr_and_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], invalid_option: list[str]
) -> None:
    source = create_image(tmp_path / "source.png")

    with pytest.raises(SystemExit) as error:
        main([str(source), "--json", *invalid_option])

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "error:" in captured.err
    assert not source.with_suffix(".svg").exists()


def test_json_preserves_cancellation_and_absent_vectorize_raster_sizes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory = tmp_path / "images"
    directory.mkdir()
    source = directory / "source.png"
    destination = directory / "source.svg"
    metric = ConversionMetrics(source, destination, 100, 80, None)
    result = BatchResult((destination,), (), metrics=(metric,), cancelled=True)
    monkeypatch.setattr(
        cli_module, "convert_directory", lambda *_args, **_kwargs: result
    )

    assert main([str(directory), "--mode", "vectorize", "--json"]) == 1

    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "vectorize"
    assert report["cancelled"] is True
    assert report["converted"][0]["embedded_raster_bytes"] is None
    assert report["sizes"] == {
        "input_bytes": 100,
        "svg_bytes": 80,
        "embedded_raster_bytes": None,
    }
