from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

import svgconverter.converter as converter_module
from svgconverter import (
    ConversionError,
    ConversionProgress,
    EmbedOptions,
    InputPathError,
    OutputCollisionError,
    OutputExistsError,
    SVGConverter,
    UnsupportedImageError,
    VectorizationDependencyError,
    VectorizeOptions,
    convert_directory,
    convert_file,
    convert_file_with_metrics,
    convert_paths,
)


def create_image(
    path: Path,
    image_format: str,
    size: tuple[int, int] = (3, 2),
    **save_kwargs: object,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, color=(25, 50, 75))
    image.save(path, format=image_format, **save_kwargs)
    return path


def embedded_raster_bytes(output_path: Path) -> bytes:
    document = output_path.read_text(encoding="utf-8")
    encoded_data = document.split("base64,", maxsplit=1)[1].split('"', maxsplit=1)[0]
    return base64.b64decode(encoded_data)


def test_convert_png_embeds_correct_mime_and_dimensions(tmp_path: Path) -> None:
    source = create_image(tmp_path / "sample.png", "PNG", (3, 2))

    output = convert_file(source)

    document = output.read_text(encoding="utf-8")
    assert output == tmp_path / "sample.svg"
    assert 'width="3" height="2"' in document
    assert "data:image/png;base64," in document


def test_default_embed_preserves_original_raster_bytes_and_reports_sizes(
    tmp_path: Path,
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG", (12, 8))

    metric = convert_file_with_metrics(source)

    assert embedded_raster_bytes(metric.output_path) == source.read_bytes()
    assert metric.input_bytes == source.stat().st_size
    assert metric.embedded_raster_bytes == source.stat().st_size
    assert metric.svg_bytes == metric.output_path.stat().st_size


def test_embed_downscales_with_preserved_aspect_ratio(tmp_path: Path) -> None:
    source = create_image(tmp_path / "source.png", "PNG", (200, 100))

    metric = convert_file_with_metrics(
        source,
        tmp_path / "result.svg",
        embed_options=EmbedOptions(max_width=150, max_height=40),
    )

    with Image.open(BytesIO(embedded_raster_bytes(metric.output_path))) as image:
        assert image.size == (80, 40)
    document = metric.output_path.read_text(encoding="utf-8")
    assert 'width="80" height="40"' in document
    assert metric.embedded_raster_bytes is not None
    assert metric.embedded_raster_bytes < metric.input_bytes


def test_embed_downscale_options_do_not_upscale_or_reencode_smaller_images(
    tmp_path: Path,
) -> None:
    source = create_image(tmp_path / "small.png", "PNG", (12, 8))

    metric = convert_file_with_metrics(
        source, embed_options=EmbedOptions(max_width=100, max_height=100)
    )

    assert embedded_raster_bytes(metric.output_path) == source.read_bytes()
    assert metric.embedded_raster_bytes == metric.input_bytes


def test_embed_jpeg_quality_reencodes_only_when_requested(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    Image.effect_noise((180, 120), 100).convert("RGB").save(source, quality=95)

    low_quality = convert_file_with_metrics(
        source,
        tmp_path / "low.svg",
        embed_options=EmbedOptions(jpeg_quality=20),
    )
    high_quality = convert_file_with_metrics(
        source,
        tmp_path / "high.svg",
        embed_options=EmbedOptions(jpeg_quality=90),
    )

    assert low_quality.embedded_raster_bytes is not None
    assert high_quality.embedded_raster_bytes is not None
    assert low_quality.embedded_raster_bytes < high_quality.embedded_raster_bytes
    with Image.open(BytesIO(embedded_raster_bytes(low_quality.output_path))) as image:
        assert image.format == "JPEG"
        assert image.size == (180, 120)


def test_embed_downscale_reencodes_jpeg_at_high_default_quality(tmp_path: Path) -> None:
    source = create_image(tmp_path / "source.jpg", "JPEG", (120, 60), quality=91)

    metric = convert_file_with_metrics(
        source,
        tmp_path / "result.svg",
        embed_options=EmbedOptions(max_width=60),
    )

    with Image.open(BytesIO(embedded_raster_bytes(metric.output_path))) as image:
        assert image.format == "JPEG"
        assert image.size == (60, 30)


def test_embed_png_compression_reencodes_pixels_without_changing_dimensions(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    image = Image.effect_noise((180, 120), 100).convert("RGB")
    image.save(source, compress_level=0)

    metric = convert_file_with_metrics(
        source,
        tmp_path / "compressed.svg",
        embed_options=EmbedOptions(png_compress_level=9, optimize_png=True),
    )

    embedded = embedded_raster_bytes(metric.output_path)
    assert metric.embedded_raster_bytes == len(embedded)
    assert metric.embedded_raster_bytes < metric.input_bytes
    with Image.open(source) as original, Image.open(BytesIO(embedded)) as compressed:
        assert compressed.format == "PNG"
        assert compressed.size == original.size
        assert compressed.tobytes() == original.tobytes()


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
    assert len(result.metrics) == 2
    assert result.total_input_bytes == sum(
        metric.input_bytes for metric in result.metrics
    )
    assert result.total_embedded_raster_bytes == sum(
        metric.embedded_raster_bytes or 0 for metric in result.metrics
    )
    assert result.total_svg_bytes == sum(metric.svg_bytes for metric in result.metrics)


def test_convert_paths_reports_progress_for_each_processed_input(
    tmp_path: Path,
) -> None:
    first = create_image(tmp_path / "first.png", "PNG")
    second = create_image(tmp_path / "second.jpg", "JPEG")
    progress_updates: list[ConversionProgress] = []

    result = convert_paths(
        [first, second],
        tmp_path / "output",
        progress_callback=progress_updates.append,
    )

    assert result.success_count == 2
    assert [update.input_path for update in progress_updates] == [first, second]
    assert [update.completed for update in progress_updates] == [1, 2]
    assert [update.total for update in progress_updates] == [2, 2]
    assert progress_updates[-1].converted == 2
    assert progress_updates[-1].skipped == 0
    assert progress_updates[-1].failed == 0


def test_convert_paths_stops_cleanly_when_cancelled_between_files(
    tmp_path: Path,
) -> None:
    first = create_image(tmp_path / "first.png", "PNG")
    second = create_image(tmp_path / "second.jpg", "JPEG")
    progress_updates: list[ConversionProgress] = []

    result = convert_paths(
        [first, second],
        tmp_path / "output",
        progress_callback=progress_updates.append,
        should_cancel=lambda: bool(progress_updates),
    )

    assert result.cancelled
    assert result.success_count == 1
    assert result.failure_count == 0
    assert len(progress_updates) == 1
    assert progress_updates[0].input_path == first
    assert not (tmp_path / "output" / "second.svg").exists()


def test_converter_facade_forwards_batch_progress_and_cancellation(
    tmp_path: Path,
) -> None:
    first = create_image(tmp_path / "first.png", "PNG")
    second = create_image(tmp_path / "second.jpg", "JPEG")
    progress_updates: list[ConversionProgress] = []

    result = SVGConverter().convert_paths(
        [first, second],
        tmp_path / "output",
        progress_callback=progress_updates.append,
        should_cancel=lambda: bool(progress_updates),
    )

    assert result.cancelled
    assert result.success_count == 1
    assert len(progress_updates) == 1


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


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_width": 0}, "max_width must be a positive integer"),
        ({"max_height": -1}, "max_height must be a positive integer"),
        ({"jpeg_quality": 96}, "jpeg_quality must be between 1 and 95"),
        (
            {"png_compress_level": 10},
            "png_compress_level must be between 0 and 9",
        ),
    ],
)
def test_embed_options_validate_requested_optimization_values(
    kwargs: dict[str, int], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        EmbedOptions(**kwargs)


def test_embed_options_are_rejected_in_vectorize_mode(tmp_path: Path) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")

    with pytest.raises(ValueError, match="embed_options can only"):
        convert_file(
            source,
            mode="vectorize",
            embed_options=EmbedOptions(max_width=100),
        )


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
