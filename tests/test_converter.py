from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

import svgconverter.converter as converter_module
from svgconverter import (
    ConversionError,
    InputPathError,
    OutputExistsError,
    SVGConverter,
    UnsupportedImageError,
    VectorizationDependencyError,
    VectorizeOptions,
    convert_directory,
    convert_file,
)


def create_image(path: Path, image_format: str, size: tuple[int, int] = (3, 2)) -> Path:
    image = Image.new("RGB", size, color=(25, 50, 75))
    image.save(path, format=image_format)
    return path


def test_convert_png_embeds_correct_mime_and_dimensions(tmp_path: Path) -> None:
    source = create_image(tmp_path / "sample.png", "PNG", (3, 2))

    output = convert_file(source)

    document = output.read_text(encoding="utf-8")
    assert output == tmp_path / "sample.svg"
    assert 'width="3" height="2"' in document
    assert "data:image/png;base64," in document


@pytest.mark.parametrize("suffix", [".jpg", ".jpeg", ".JPG"])
def test_convert_jpeg_uses_jpeg_mime_type(tmp_path: Path, suffix: str) -> None:
    source = create_image(tmp_path / f"photo{suffix}", "JPEG")

    output = convert_file(source)

    assert "data:image/jpeg;base64," in output.read_text(encoding="utf-8")


def test_mime_type_is_detected_from_image_content(tmp_path: Path) -> None:
    source = create_image(tmp_path / "misnamed.jpg", "PNG")

    output = convert_file(source)

    assert "data:image/png;base64," in output.read_text(encoding="utf-8")


def test_explicit_output_creates_parent_directories(tmp_path: Path) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    destination = tmp_path / "nested" / "result.svg"

    output = convert_file(source, destination)

    assert output == destination
    assert output.is_file()


def test_existing_output_requires_overwrite(tmp_path: Path) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    destination = tmp_path / "result.svg"
    destination.write_text("original", encoding="utf-8")

    with pytest.raises(OutputExistsError):
        convert_file(source, destination)

    convert_file(source, destination, overwrite=True)
    assert "data:image/png;base64," in destination.read_text(encoding="utf-8")


def test_invalid_inputs_raise_useful_errors(tmp_path: Path) -> None:
    with pytest.raises(InputPathError):
        convert_file(tmp_path / "missing.png")

    text_file = tmp_path / "not-an-image.gif"
    text_file.write_text("not an image", encoding="utf-8")
    with pytest.raises(UnsupportedImageError):
        convert_file(text_file)

    corrupt_image = tmp_path / "corrupt.png"
    corrupt_image.write_bytes(b"not a PNG")
    with pytest.raises(ConversionError, match="Cannot read image"):
        convert_file(corrupt_image)


def test_directory_conversion_reports_successes_and_failures(tmp_path: Path) -> None:
    source_directory = tmp_path / "images"
    source_directory.mkdir()
    create_image(source_directory / "one.png", "PNG")
    create_image(source_directory / "two.JPEG", "JPEG")
    (source_directory / "bad.jpg").write_bytes(b"not an image")
    (source_directory / "ignored.txt").write_text("ignored", encoding="utf-8")
    output_directory = tmp_path / "converted"

    result = convert_directory(source_directory, output_directory)

    assert result.success_count == 2
    assert result.failure_count == 1
    assert {path.name for path in result.converted} == {"one.svg", "two.svg"}
    assert result.failed[0].input_path.name == "bad.jpg"
    assert (output_directory / "one.svg").is_file()


def test_converter_class_uses_its_configuration(tmp_path: Path) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    destination = tmp_path / "result.svg"
    destination.write_text("old", encoding="utf-8")

    output = SVGConverter(overwrite=True).convert_file(source, destination)

    assert output == destination
    assert "data:image/png;base64," in destination.read_text(encoding="utf-8")


def test_unknown_conversion_mode_is_rejected(tmp_path: Path) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")

    with pytest.raises(ValueError, match="either 'embed' or 'vectorize'"):
        convert_file(source, mode="unknown")  # type: ignore[arg-type]


def test_vectorize_mode_explains_missing_optional_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")

    def raise_missing_module(_: str) -> object:
        raise ModuleNotFoundError("No module named 'vtracer'")

    monkeypatch.setattr(
        converter_module.importlib, "import_module", raise_missing_module
    )

    with pytest.raises(
        VectorizationDependencyError, match=r"svgconverter\[vectorize\]"
    ):
        convert_file(source, mode="vectorize")


def test_vectorize_options_map_to_stable_backend_arguments() -> None:
    options = VectorizeOptions(
        color_mode="binary",
        hierarchical="cutout",
        curve_mode="polygon",
        filter_speckle=4,
        color_precision=6,
        layer_difference=16,
        path_precision=3,
    )

    assert options.as_vtracer_kwargs() == {
        "colormode": "binary",
        "hierarchical": "cutout",
        "mode": "polygon",
        "filter_speckle": 4,
        "color_precision": 6,
        "layer_difference": 16,
        "path_precision": 3,
    }
