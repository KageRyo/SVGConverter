from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

import svgconverter.converter as converter_module
from svgconverter import (
    ConversionError,
    InputPathError,
    OutputCollisionError,
    OutputExistsError,
    SVGConverter,
    UnsupportedImageError,
    VectorizationDependencyError,
    VectorizeOptions,
    convert_directory,
    convert_file,
    convert_paths,
)


def create_image(path: Path, image_format: str, size: tuple[int, int] = (3, 2)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
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


@pytest.mark.parametrize(
    ("suffix", "image_format", "mime_type"),
    [
        (".webp", "WEBP", "image/webp"),
        (".bmp", "BMP", "image/bmp"),
        (".tif", "TIFF", "image/tiff"),
        (".tiff", "TIFF", "image/tiff"),
    ],
)
def test_additional_raster_formats_use_correct_mime_type(
    tmp_path: Path, suffix: str, image_format: str, mime_type: str
) -> None:
    source = create_image(tmp_path / f"sample{suffix}", image_format)

    output = convert_file(source)

    assert f"data:{mime_type};base64," in output.read_text(encoding="utf-8")


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
    with pytest.raises(
        UnsupportedImageError, match=r"Unsupported image extension.*\.webp"
    ):
        convert_file(text_file)

    disguised_gif = create_image(tmp_path / "disguised.png", "GIF")
    with pytest.raises(UnsupportedImageError, match="Unsupported image format.*GIF"):
        convert_file(disguised_gif)

    corrupt_image = tmp_path / "corrupt.png"
    corrupt_image.write_bytes(b"not a PNG")
    with pytest.raises(ConversionError, match="Cannot read image"):
        convert_file(corrupt_image)


def test_directory_conversion_reports_successes_and_failures(tmp_path: Path) -> None:
    source_directory = tmp_path / "images"
    source_directory.mkdir()
    create_image(source_directory / "one.png", "PNG")
    create_image(source_directory / "two.JPEG", "JPEG")
    create_image(source_directory / "three.webp", "WEBP")
    create_image(source_directory / "four.bmp", "BMP")
    create_image(source_directory / "five.tiff", "TIFF")
    (source_directory / "bad.jpg").write_bytes(b"not an image")
    (source_directory / "ignored.txt").write_text("ignored", encoding="utf-8")
    output_directory = tmp_path / "converted"

    result = convert_directory(source_directory, output_directory)

    assert result.success_count == 5
    assert result.failure_count == 1
    assert {path.name for path in result.converted} == {
        "one.svg",
        "two.svg",
        "three.svg",
        "four.svg",
        "five.svg",
    }
    assert result.failed[0].input_path.name == "bad.jpg"
    assert (output_directory / "one.svg").is_file()


def test_recursive_directory_conversion_preserves_relative_output_paths(
    tmp_path: Path,
) -> None:
    source_directory = tmp_path / "images"
    create_image(source_directory / "top.png", "PNG")
    create_image(source_directory / "one" / "logo.png", "PNG")
    create_image(source_directory / "two" / "logo.png", "PNG")

    non_recursive_output = tmp_path / "non-recursive"
    non_recursive_result = convert_directory(source_directory, non_recursive_output)

    assert non_recursive_result.success_count == 1
    assert (non_recursive_output / "top.svg").is_file()
    assert not (non_recursive_output / "one" / "logo.svg").exists()

    recursive_output = tmp_path / "recursive"
    recursive_result = convert_directory(
        source_directory, recursive_output, recursive=True
    )

    assert recursive_result.success_count == 3
    assert (recursive_output / "top.svg").is_file()
    assert (recursive_output / "one" / "logo.svg").is_file()
    assert (recursive_output / "two" / "logo.svg").is_file()


def test_directory_conversion_skips_existing_outputs_unless_overwriting(
    tmp_path: Path,
) -> None:
    source_directory = tmp_path / "images"
    create_image(source_directory / "sample.png", "PNG")
    output_directory = tmp_path / "output"
    output_directory.mkdir()
    destination = output_directory / "sample.svg"
    destination.write_text("existing output", encoding="utf-8")

    skipped_result = convert_directory(source_directory, output_directory)

    assert skipped_result.success_count == 0
    assert skipped_result.skipped_count == 1
    assert skipped_result.failure_count == 0
    assert skipped_result.skipped[0].input_path == source_directory / "sample.png"
    assert skipped_result.skipped[0].output_path == destination
    assert destination.read_text(encoding="utf-8") == "existing output"

    overwritten_result = convert_directory(
        source_directory, output_directory, overwrite=True
    )

    assert overwritten_result.success_count == 1
    assert overwritten_result.skipped_count == 0
    assert "data:image/png;base64," in destination.read_text(encoding="utf-8")


def test_convert_paths_converts_multiple_input_files_to_one_output_directory(
    tmp_path: Path,
) -> None:
    first = create_image(tmp_path / "first.png", "PNG")
    second = create_image(tmp_path / "second.jpg", "JPEG")
    output_directory = tmp_path / "output"

    result = convert_paths([first, second], output_directory)

    assert result.success_count == 2
    assert result.skipped_count == 0
    assert result.failure_count == 0
    assert (output_directory / "first.svg").is_file()
    assert (output_directory / "second.svg").is_file()


def test_convert_paths_keeps_multiple_directory_trees_separate(
    tmp_path: Path,
) -> None:
    first_directory = tmp_path / "first"
    second_directory = tmp_path / "second"
    create_image(first_directory / "nested" / "logo.png", "PNG")
    create_image(second_directory / "nested" / "logo.png", "PNG")
    output_directory = tmp_path / "output"

    result = convert_paths(
        [first_directory, second_directory], output_directory, recursive=True
    )

    assert result.success_count == 2
    assert result.failure_count == 0
    assert (output_directory / "first" / "nested" / "logo.svg").is_file()
    assert (output_directory / "second" / "nested" / "logo.svg").is_file()


def test_convert_paths_reports_output_collisions_without_writing(
    tmp_path: Path,
) -> None:
    png = create_image(tmp_path / "image.png", "PNG")
    jpeg = create_image(tmp_path / "image.jpg", "JPEG")
    output_directory = tmp_path / "output"

    result = convert_paths([png, jpeg], output_directory)

    assert result.success_count == 0
    assert result.failure_count == 2
    assert all(
        isinstance(failure.error, OutputCollisionError) for failure in result.failed
    )
    assert not (output_directory / "image.svg").exists()


def test_converter_class_uses_its_configuration(tmp_path: Path) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    destination = tmp_path / "result.svg"
    destination.write_text("old", encoding="utf-8")

    output = SVGConverter(overwrite=True).convert_file(source, destination)

    assert output == destination
    assert "data:image/png;base64," in destination.read_text(encoding="utf-8")


def test_converter_class_can_configure_recursive_directory_conversion(
    tmp_path: Path,
) -> None:
    source_directory = tmp_path / "images"
    create_image(source_directory / "nested" / "sample.png", "PNG")
    output_directory = tmp_path / "output"

    result = SVGConverter(recursive=True).convert_directory(
        source_directory, output_directory
    )

    assert result.success_count == 1
    assert (output_directory / "nested" / "sample.svg").is_file()


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
