from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from svgconverter import SVGConverter, VectorizeOptions, convert_directory, convert_file
from svgconverter.cli import main

pytest.importorskip("vtracer")


def create_line_art(path: Path, image_format: str = "PNG") -> Path:
    image = Image.new("RGB", (32, 32), "white")
    ImageDraw.Draw(image).ellipse((4, 4, 28, 28), fill="black")
    image.save(path, format=image_format)
    return path


def assert_is_vector_svg(path: Path) -> None:
    document = path.read_text(encoding="utf-8")
    assert "<path" in document
    assert "<image" not in document
    assert "base64," not in document


@pytest.mark.parametrize(
    ("filename", "image_format"),
    [
        ("logo.png", "PNG"),
        ("photo.jpg", "JPEG"),
        ("image.webp", "WEBP"),
        ("image.bmp", "BMP"),
        ("image.tiff", "TIFF"),
    ],
)
def test_vectorize_file_creates_svg_paths(
    tmp_path: Path, filename: str, image_format: str
) -> None:
    source = create_line_art(tmp_path / filename, image_format)

    output = convert_file(
        source,
        mode="vectorize",
        vectorize_options=VectorizeOptions(
            color_mode="binary", curve_mode="polygon", path_precision=3
        ),
    )

    assert output == tmp_path / f"{Path(filename).stem}.svg"
    assert_is_vector_svg(output)


def test_vectorize_directory_and_converter_class(tmp_path: Path) -> None:
    source_directory = tmp_path / "images"
    source_directory.mkdir()
    create_line_art(source_directory / "one.png")
    create_line_art(source_directory / "two.png")
    output_directory = tmp_path / "out"

    result = convert_directory(
        source_directory,
        output_directory,
        mode="vectorize",
    )
    class_output = SVGConverter(mode="vectorize").convert_file(
        source_directory / "one.png", tmp_path / "class-output.svg"
    )

    assert result.success_count == 2
    assert result.failure_count == 0
    assert_is_vector_svg(output_directory / "one.svg")
    assert_is_vector_svg(class_output)


def test_cli_vectorize_mode_creates_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = create_line_art(tmp_path / "logo.png")
    destination = tmp_path / "logo.svg"

    exit_code = main(
        [
            str(source),
            "--output",
            str(destination),
            "--mode",
            "vectorize",
            "--vectorize-color-mode",
            "binary",
            "--vectorize-curve-mode",
            "polygon",
        ]
    )

    assert exit_code == 0
    assert "Converted:" in capsys.readouterr().out
    assert_is_vector_svg(destination)
