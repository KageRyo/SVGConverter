from __future__ import annotations

import base64
import builtins
import io
import socket
from io import BytesIO
from pathlib import Path

import pytest
from PIL import ExifTags, Image

import svgconverter.converter as converter_module
import svgconverter.embed as embed_module
import svgconverter.vectorize as vectorize_module
from svgconverter import (
    BatchResult,
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
from svgconverter.errors import ConversionError as ErrorConversionError
from svgconverter.errors import SVGConverterError as ErrorBase
from svgconverter.models import BatchResult as ModelBatchResult
from svgconverter.models import ConversionMode
from svgconverter.models import EmbedOptions as ModelEmbedOptions


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


def test_public_models_and_errors_remain_reexported() -> None:
    assert BatchResult is ModelBatchResult
    assert EmbedOptions is ModelEmbedOptions
    assert ConversionError is ErrorConversionError
    assert issubclass(ConversionError, ErrorBase)


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


@pytest.mark.parametrize(
    ("suffix", "image_format"),
    [(".png", "PNG"), (".jpg", "JPEG"), (".webp", "WEBP"), (".bmp", "BMP")],
)
def test_default_embed_preserves_original_raster_bytes_and_reports_sizes(
    tmp_path: Path, suffix: str, image_format: str
) -> None:
    source = create_image(tmp_path / f"sample{suffix}", image_format, (12, 8))

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


@pytest.mark.parametrize(
    ("suffix", "image_format"),
    [(".png", "PNG"), (".jpg", "JPEG"), (".webp", "WEBP"), (".bmp", "BMP")],
)
def test_embed_downscale_options_do_not_upscale_or_reencode_smaller_images(
    tmp_path: Path, suffix: str, image_format: str
) -> None:
    source = create_image(tmp_path / f"small{suffix}", image_format, (12, 8))

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


def create_rotated_jpeg(path: Path, orientation: int) -> Path:
    """Store a 40x20 JPEG whose EXIF orientation displays it differently."""

    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = orientation
    return create_image(path, "JPEG", (40, 20), exif=exif.tobytes())


@pytest.mark.parametrize(
    ("orientation", "expected_size"),
    [(1, (40, 20)), (3, (40, 20)), (5, (20, 40)), (6, (20, 40)), (8, (20, 40))],
)
def test_embed_uses_exif_oriented_display_dimensions(
    tmp_path: Path, orientation: int, expected_size: tuple[int, int]
) -> None:
    source = create_rotated_jpeg(tmp_path / "photo.jpg", orientation)

    output = convert_file(source)

    width, height = expected_size
    document = output.read_text(encoding="utf-8")
    assert f'width="{width}" height="{height}" viewBox="0 0 {width} {height}"' in (
        document
    )
    assert '<image href="data:image/jpeg;base64,' in document
    assert f'width="{width}" height="{height}"/>' in document
    assert embedded_raster_bytes(output) == source.read_bytes()


def test_embed_reencoding_applies_exif_orientation_before_resizing(
    tmp_path: Path,
) -> None:
    source = create_rotated_jpeg(tmp_path / "photo.jpg", 6)

    metric = convert_file_with_metrics(source, embed_options=EmbedOptions(max_width=10))

    document = metric.output_path.read_text(encoding="utf-8")
    assert 'width="10" height="20"' in document
    with Image.open(BytesIO(embedded_raster_bytes(metric.output_path))) as image:
        assert image.size == (10, 20)
        assert image.getexif().get(ExifTags.Base.Orientation, 1) == 1


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
        (".tif", "TIFF", "image/png"),
        (".tiff", "TIFF", "image/png"),
    ],
)
def test_additional_raster_formats_use_correct_mime_type(
    tmp_path: Path, suffix: str, image_format: str, mime_type: str
) -> None:
    source = create_image(tmp_path / f"sample{suffix}", image_format)

    output = convert_file(source)

    assert f"data:{mime_type};base64," in output.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("mode", "color", "expected_mode"),
    [
        ("RGB", (25, 50, 75), "RGB"),
        ("RGBA", (25, 50, 75, 128), "RGBA"),
        ("L", 90, "L"),
        ("I;16", 40000, "I;16"),
        ("CMYK", (0, 128, 255, 0), "RGB"),
        ("LAB", (50, 128, 128), "RGB"),
        ("PA", (0, 128), "RGBA"),
    ],
)
def test_tiff_is_embedded_as_lossless_png(
    tmp_path: Path, mode: str, color: object, expected_mode: str
) -> None:
    source = tmp_path / "scan.tiff"
    Image.new(mode, (6, 4), color).save(source, format="TIFF")

    metric = convert_file_with_metrics(source)

    document = metric.output_path.read_text(encoding="utf-8")
    assert "data:image/png;base64," in document
    assert 'width="6" height="4"' in document
    embedded = embedded_raster_bytes(metric.output_path)
    assert metric.embedded_raster_bytes == len(embedded)
    with Image.open(source) as original, Image.open(BytesIO(embedded)) as png:
        assert png.format == "PNG"
        assert png.mode == expected_mode
        expected = (
            original
            if original.mode == expected_mode
            else original.convert(expected_mode)
        )
        assert png.tobytes() == expected.tobytes()


def test_tiff_colour_conversion_drops_the_source_colour_profile(
    tmp_path: Path,
) -> None:
    source = tmp_path / "print.tiff"
    Image.new("CMYK", (4, 4)).save(source, format="TIFF", icc_profile=b"cmyk-icc")
    with Image.open(source) as original:
        assert original.info.get("icc_profile") == b"cmyk-icc"

    output = convert_file(source)

    with Image.open(BytesIO(embedded_raster_bytes(output))) as png:
        assert png.mode == "RGB"
        assert "icc_profile" not in png.info


def test_multipage_tiff_embeds_the_first_page(tmp_path: Path) -> None:
    source = tmp_path / "pages.tiff"
    first = Image.new("RGB", (4, 4), (255, 0, 0))
    second = Image.new("RGB", (8, 8), (0, 0, 255))
    first.save(source, format="TIFF", save_all=True, append_images=[second])

    output = convert_file(source)

    assert 'width="4" height="4"' in output.read_text(encoding="utf-8")
    with Image.open(BytesIO(embedded_raster_bytes(output))) as png:
        assert png.format == "PNG"
        assert png.size == (4, 4)
        assert png.getpixel((0, 0)) == (255, 0, 0)


def test_tiff_embed_options_resize_into_png(tmp_path: Path) -> None:
    source = create_image(tmp_path / "scan.tif", "TIFF", (40, 20))

    output = convert_file(source, embed_options=EmbedOptions(max_width=10))

    assert 'width="10" height="5"' in output.read_text(encoding="utf-8")
    with Image.open(BytesIO(embedded_raster_bytes(output))) as png:
        assert png.format == "PNG"
        assert png.size == (10, 5)


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


def test_allowed_root_rejects_input_outside_boundary(tmp_path: Path) -> None:
    allowed_root = tmp_path / "workspace"
    allowed_root.mkdir()
    source = create_image(tmp_path / "outside.png", "PNG")

    with pytest.raises(InputPathError, match="within allowed root"):
        convert_file(source, allowed_root=allowed_root)


def test_allowed_root_rejects_output_outside_boundary(tmp_path: Path) -> None:
    allowed_root = tmp_path / "workspace"
    allowed_root.mkdir()
    source = create_image(allowed_root / "sample.png", "PNG")
    destination = allowed_root / ".." / "outside.svg"

    with pytest.raises(InputPathError, match="within allowed root"):
        convert_file(source, destination, allowed_root=allowed_root)

    assert not destination.resolve().exists()


def test_allowed_root_rejects_symlink_escape(tmp_path: Path) -> None:
    allowed_root = tmp_path / "workspace"
    allowed_root.mkdir()
    outside_source = create_image(tmp_path / "outside.png", "PNG")
    linked_source = allowed_root / "linked.png"
    try:
        linked_source.symlink_to(outside_source)
    except OSError as error:
        pytest.skip(f"symlink creation is unavailable: {error}")

    with pytest.raises(InputPathError, match="within allowed root"):
        convert_file(linked_source, allowed_root=allowed_root)


def test_allowed_root_accepts_paths_after_normalizing_inside_traversal(
    tmp_path: Path,
) -> None:
    allowed_root = tmp_path / "workspace"
    source = create_image(allowed_root / "images" / "sample.png", "PNG")
    destination = allowed_root / "output" / ".." / "result.svg"

    output = convert_file(source, destination, allowed_root=allowed_root)

    assert output == allowed_root / "result.svg"
    assert output.is_file()


def test_allowed_root_applies_to_batch_conversion(tmp_path: Path) -> None:
    allowed_root = tmp_path / "workspace"
    source = create_image(allowed_root / "images" / "sample.png", "PNG")
    output_directory = allowed_root / "output"

    result = convert_paths([source], output_directory, allowed_root=allowed_root)

    assert result.success_count == 1
    assert result.converted == (output_directory / "sample.svg",)


def test_existing_output_requires_overwrite(tmp_path: Path) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    destination = tmp_path / "result.svg"
    destination.write_text("original", encoding="utf-8")

    with pytest.raises(OutputExistsError):
        convert_file(source, destination)

    convert_file(source, destination, overwrite=True)
    assert "data:image/png;base64," in destination.read_text(encoding="utf-8")


def test_failed_embed_does_not_leave_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    destination = tmp_path / "result.svg"

    def fail_after_partial_write(
        _source: Path, temporary_path: Path, _options: EmbedOptions | None
    ) -> int:
        temporary_path.write_text("partial", encoding="utf-8")
        raise ConversionError("embed backend failed")

    monkeypatch.setattr(converter_module, "embed_image", fail_after_partial_write)

    with pytest.raises(ConversionError) as error_info:
        convert_file(source, destination)

    assert str(source) in str(error_info.value)
    assert str(destination) in str(error_info.value)
    assert not destination.exists()
    assert not list(tmp_path.glob(".result-*.svg.tmp"))


def test_failed_vectorize_preserves_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    destination = tmp_path / "result.svg"
    destination.write_text("original", encoding="utf-8")

    def fail_after_partial_write(
        _source: Path, temporary_path: Path, _options: VectorizeOptions
    ) -> None:
        temporary_path.write_text("partial", encoding="utf-8")
        raise ConversionError("vectorize backend failed")

    monkeypatch.setattr(converter_module, "vectorize_image", fail_after_partial_write)

    with pytest.raises(ConversionError) as error_info:
        convert_file(source, destination, mode="vectorize", overwrite=True)

    assert str(source) in str(error_info.value)
    assert str(destination) in str(error_info.value)
    assert destination.read_text(encoding="utf-8") == "original"
    assert not list(tmp_path.glob(".result-*.svg.tmp"))


def stage_svg_document(monkeypatch: pytest.MonkeyPatch, document: bytes) -> None:
    """Substitute successful conversion backends."""

    def write_embed(
        _source: Path, destination: Path, _options: EmbedOptions | None
    ) -> int:
        """Write staged embed output."""

        destination.write_bytes(document)
        return 0

    def write_vectorize(
        _source: Path, destination: Path, _options: VectorizeOptions
    ) -> None:
        """Write staged vector output."""

        destination.write_bytes(document)

    monkeypatch.setattr(converter_module, "embed_image", write_embed)
    monkeypatch.setattr(converter_module, "vectorize_image", write_vectorize)


@pytest.mark.parametrize("mode", ["embed", "vectorize"])
@pytest.mark.parametrize("existing_output", [False, True], ids=["new", "existing"])
@pytest.mark.parametrize(
    ("document", "message"),
    [
        pytest.param(b"", "empty SVG", id="empty"),
        pytest.param(
            b'<svg xmlns="http://www.w3.org/2000/svg">',
            "Invalid SVG XML",
            id="unclosed-root",
        ),
        pytest.param(
            b'<svg xmlns="http://www.w3.org/2000/svg"><path></svg>',
            "Invalid SVG XML",
            id="mismatched-tags",
        ),
        pytest.param(
            b'<svg xmlns="http://www.w3.org/2000/svg"/><!--',
            "Invalid SVG XML",
            id="malformed-trailing-content",
        ),
        pytest.param(
            b'<html xmlns="http://www.w3.org/2000/svg"/>',
            "SVG root",
            id="wrong-root",
        ),
        pytest.param(b"<svg/>", "SVG root", id="missing-namespace"),
        pytest.param(
            b'<!DOCTYPE html SYSTEM "unused.dtd">'
            b'<html xmlns="http://www.w3.org/2000/svg"/>',
            "SVG root",
            id="wrong-root-with-doctype",
        ),
        pytest.param(
            b'<svg xmlns="urn:another-format"/>', "SVG root", id="wrong-namespace"
        ),
        pytest.param(
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            + b'<path d="M0 0 L1 1"/>' * 10000
            + b"</broken>",
            "Invalid SVG XML",
            id="late-malformed-xml",
        ),
        pytest.param(
            b'<!DOCTYPE svg SYSTEM "unused.dtd">'
            b'<svg xmlns="http://www.w3.org/2000/svg" title="&missing;"/>',
            "Invalid SVG XML",
            id="unresolved-root-attribute",
        ),
        pytest.param(
            (
                '<!DOCTYPE svg SYSTEM "unused.dtd">'
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<path d="&missing;"/></svg>'
            ).encode("utf-16"),
            "Invalid SVG XML",
            id="unresolved-child-attribute-utf16",
        ),
        pytest.param(
            b'<!DOCTYPE svg SYSTEM "unused.dtd" [%missing;]>'
            b'<svg xmlns="http://www.w3.org/2000/svg"/>',
            "entity references",
            id="unresolved-parameter-reference",
        ),
        pytest.param(
            b'<!DOCTYPE svg SYSTEM "unused.dtd" '
            b'[<!ATTLIST svg title CDATA "&missing;">]>'
            b'<svg xmlns="http://www.w3.org/2000/svg"/>',
            "Invalid SVG XML",
            id="unresolved-default-attribute",
        ),
        pytest.param(
            b'<?xml version="1.0" encoding="not-an-encoding"?>'
            b'<svg xmlns="http://www.w3.org/2000/svg"/>',
            "Invalid SVG XML",
            id="unknown-encoding",
        ),
        pytest.param(
            b'<?xml version="1.0" encoding="UTF-7"?>'
            b'<svg xmlns="http://www.w3.org/2000/svg"/>',
            "Invalid SVG XML",
            id="unsupported-encoding",
        ),
    ],
)
def test_invalid_staged_svg_preserves_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: ConversionMode,
    existing_output: bool,
    document: bytes,
    message: str,
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    destination = tmp_path / "result.svg"
    original = b'<svg xmlns="http://www.w3.org/2000/svg"><title>Original</title></svg>'
    if existing_output:
        destination.write_bytes(original)
    stage_svg_document(monkeypatch, document)

    with pytest.raises(ConversionError, match=message) as error:
        convert_file(source, destination, mode=mode, overwrite=existing_output)

    assert str(source) in str(error.value)
    assert str(destination) in str(error.value)
    if existing_output:
        assert destination.read_bytes() == original
    else:
        assert not destination.exists()
    assert not list(tmp_path.glob(".result-*.svg.tmp"))


@pytest.mark.parametrize("mode", ["embed", "vectorize"])
@pytest.mark.parametrize("encoding", ["not-an-encoding", "UTF-7"])
def test_invalid_svg_encoding_does_not_stop_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: ConversionMode,
    encoding: str,
) -> None:
    sources = [
        create_image(tmp_path / "first.png", "PNG"),
        create_image(tmp_path / "second.png", "PNG"),
    ]
    output_directory = tmp_path / "output"
    document = (
        f'<?xml version="1.0" encoding="{encoding}"?>'
        '<svg xmlns="http://www.w3.org/2000/svg"/>'
    ).encode()
    stage_svg_document(monkeypatch, document)

    result = convert_paths(sources, output_directory, mode=mode)

    assert result.success_count == 0
    assert result.failure_count == 2
    assert [failure.input_path for failure in result.failed] == sources
    for failure in result.failed:
        destination = output_directory / failure.input_path.with_suffix(".svg").name
        assert isinstance(failure.error, ConversionError)
        assert str(failure.input_path) in str(failure.error)
        assert str(destination) in str(failure.error)
        assert not destination.exists()
    assert not list(output_directory.glob(".*.svg.tmp"))


@pytest.mark.parametrize("mode", ["embed", "vectorize"])
@pytest.mark.parametrize(
    "document",
    [
        pytest.param(b'<svg xmlns="http://www.w3.org/2000/svg"/>', id="empty-svg"),
        pytest.param(
            b'<?xml version="1.0"?><!-- optional --><?renderer option?>'
            b'<s:svg xmlns:s="http://www.w3.org/2000/svg" xmlns:x="urn:extension" '
            b'custom="yes"><s:title>A &amp; B &#65;</s:title>'
            b"<x:metadata/><s:style><![CDATA[path {fill: red;}]]></s:style>"
            b'<s:path d="M0 0 L1 1"/></s:svg>',
            id="optional-contents",
        ),
        pytest.param(
            '<svg xmlns="http://www.w3.org/2000/svg"><title>画像</title></svg>'.encode(
                "utf-16"
            ),
            id="utf16",
        ),
        pytest.param(
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            + b'<path d="M0 0 L1 1"/>' * 10000
            + b"</svg>",
            id="many-paths",
        ),
        pytest.param(
            (
                '<?xml version="1.0" encoding="UTF-16"?>'
                '<!DOCTYPE s:svg PUBLIC "SVG" "unused.dtd" '
                '[<!ATTLIST s:svg title CDATA "A &amp; B">]>'
                '<s:svg xmlns:s="http://www.w3.org/2000/svg" '
                'literal="&amp;missing;"><s:style><![CDATA[&missing;]]>'
                "</s:style><!-- &missing; --><?renderer &missing;?></s:svg>"
            ).encode("utf-16"),
            id="external-doctype-utf16",
        ),
        pytest.param(
            b'<!DOCTYPE svg SYSTEM "unused.dtd" '
            b'[<!ATTLIST svg xmlns CDATA "http://www.w3.org/2000/svg">]>'
            b'<svg><path d="M0 0 L1 1"/></svg>',
            id="doctype-default-namespace",
        ),
        pytest.param(
            b'<!DOCTYPE svg SYSTEM "unused.dtd">'
            b'<svg xmlns="http://www.w3.org/2000/svg" title="'
            + b"A" * 40000
            + b'">'
            + b'<path d="M0 0 L1 1"/>' * 10000
            + b"</svg>",
            id="large-external-doctype",
        ),
        pytest.param(
            b'<!DOCTYPE s:svg SYSTEM "unused.dtd" ['
            b'<!-- first --><!ENTITY amp "&#38;#38;">'
            b"<!ELEMENT s:svg ANY><?renderer option?>"
            b'<!NOTATION format SYSTEM "unused.format">'
            b'<!ATTLIST s:svg xmlns:s CDATA "http://www.w3.org/2000/svg" '
            b'title CDATA "a>b"><!-- last -->]><s:svg/>',
            id="mixed-doctype-declarations",
        ),
    ],
)
def test_valid_staged_svg_is_published_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: ConversionMode,
    document: bytes,
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    stage_svg_document(monkeypatch, document)

    output = convert_file(source, mode=mode)

    assert output.read_bytes() == document
    assert not list(tmp_path.glob(".sample-*.svg.tmp"))


@pytest.mark.parametrize("mode", ["embed", "vectorize"])
@pytest.mark.parametrize("existing_output", [False, True], ids=["new", "existing"])
@pytest.mark.parametrize("quote", ["'", '"'], ids=["single", "double"])
@pytest.mark.parametrize("encoding", ["utf-16", "cp1251"])
def test_fragmented_doctype_literals_are_published_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: ConversionMode,
    existing_output: bool,
    quote: str,
    encoding: str,
) -> None:
    opposite_quote = '"' if quote == "'" else "'"
    identifier = "A" * 1023 + "<!" + "B" * 1021 + ">" + "C" * 1500 + opposite_quote
    declared_encoding = "UTF-16" if encoding == "utf-16" else "windows-1251"
    document = (
        f'<?xml version="1.0" encoding="{declared_encoding}"?>'
        '<!DOCTYPE svg SYSTEM "unused.dtd" ['
        f"<!NOTATION format SYSTEM {quote}{identifier}{quote}>"
        '<!ATTLIST svg xmlns CDATA "http://www.w3.org/2000/svg">]><svg/>'
    ).encode(encoding)
    source = create_image(tmp_path / "sample.png", "PNG")
    destination = tmp_path / "result.svg"
    if existing_output:
        destination.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>')
    stage_svg_document(monkeypatch, document)

    output = convert_file(source, destination, mode=mode, overwrite=existing_output)

    assert output == destination
    assert output.read_bytes() == document
    assert not list(tmp_path.glob(".result-*.svg.tmp"))


@pytest.mark.parametrize("mode", ["embed", "vectorize"])
@pytest.mark.parametrize("existing_output", [False, True], ids=["new", "existing"])
@pytest.mark.parametrize("content_type", ["comment", "instruction", "attribute"])
def test_long_doctype_contents_are_published_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: ConversionMode,
    existing_output: bool,
    content_type: str,
) -> None:
    content = "Ж>x" * 2000
    if content_type == "comment":
        declaration = f"<!--{content}-->"
    elif content_type == "instruction":
        declaration = f"<?renderer {content}?>"
    else:
        declaration = f'<!ATTLIST svg title CDATA "{content}">'
    document = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<!DOCTYPE svg SYSTEM "unused.dtd" ['
        '<!ATTLIST svg xmlns CDATA "http://www.w3.org/2000/svg">'
        f'{declaration}<!ENTITY amp "&#38;#38;">]><svg/>'
    ).encode("utf-16")
    source = create_image(tmp_path / "sample.png", "PNG")
    destination = tmp_path / "result.svg"
    if existing_output:
        destination.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>')
    stage_svg_document(monkeypatch, document)

    output = convert_file(source, destination, mode=mode, overwrite=existing_output)

    assert output == destination
    assert output.read_bytes() == document
    assert not list(tmp_path.glob(".result-*.svg.tmp"))


@pytest.mark.parametrize("mode", ["embed", "vectorize"])
@pytest.mark.parametrize("existing_output", [False, True], ids=["new", "existing"])
@pytest.mark.parametrize("declaration_first", [False, True], ids=["after", "before"])
def test_svg_rejects_parameter_entity_before_expansion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: ConversionMode,
    existing_output: bool,
    declaration_first: bool,
) -> None:
    support = '<!ATTLIST svg xmlns CDATA "http://www.w3.org/2000/svg"><!-- comment -->'
    entity = '<!ENTITY % evil "&#60;!ELEMENT svg ANY>">%evil;'
    declarations = entity + support if declaration_first else support + entity
    document = (f'<!DOCTYPE svg SYSTEM "unused.dtd" [{declarations}]><svg/>').encode()
    source = create_image(tmp_path / "sample.png", "PNG")
    destination = tmp_path / "result.svg"
    original = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
    if existing_output:
        destination.write_bytes(original)
    observed_declarations: list[str] = []
    create_parser = converter_module.expat.ParserCreate

    def observe_parser(
        *args: object, **kwargs: object
    ) -> converter_module.expat.XMLParserType:
        """Observe real declaration parsing."""

        parser = create_parser(*args, **kwargs)
        parser.ElementDeclHandler = lambda name, _model: observed_declarations.append(
            name
        )
        return parser

    control = observe_parser()
    control.SetParamEntityParsing(
        converter_module.expat.XML_PARAM_ENTITY_PARSING_ALWAYS
    )
    control.Parse(document, True)
    assert observed_declarations == ["svg"]
    observed_declarations.clear()
    monkeypatch.setattr(converter_module.expat, "ParserCreate", observe_parser)
    stage_svg_document(monkeypatch, document)

    with pytest.raises(ConversionError, match="entity declarations"):
        convert_file(source, destination, mode=mode, overwrite=existing_output)

    assert observed_declarations == []
    if existing_output:
        assert destination.read_bytes() == original
    else:
        assert not destination.exists()
    assert not list(tmp_path.glob(".result-*.svg.tmp"))


@pytest.mark.parametrize("mode", ["embed", "vectorize"])
@pytest.mark.parametrize("existing_output", [False, True], ids=["new", "existing"])
@pytest.mark.parametrize(
    ("name", "replacement"),
    [
        ("amp", "&#38;#38;"),
        ("lt", "&#38;#60;"),
        ("gt", "&#62;"),
        ("apos", "&#39;"),
        ("quot", "&#34;"),
    ],
)
def test_predefined_svg_entities_are_published_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: ConversionMode,
    existing_output: bool,
    name: str,
    replacement: str,
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    destination = tmp_path / "result.svg"
    if existing_output:
        destination.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>')
    document = (
        f'<!DOCTYPE svg SYSTEM "unused.dtd" [<!ENTITY {name} "{replacement}">]>'
        f'<svg xmlns="http://www.w3.org/2000/svg">&{name};</svg>'
    ).encode()
    stage_svg_document(monkeypatch, document)

    output = convert_file(source, destination, mode=mode, overwrite=existing_output)

    assert output == destination
    assert output.read_bytes() == document
    assert not list(tmp_path.glob(".result-*.svg.tmp"))


@pytest.mark.parametrize("mode", ["embed", "vectorize"])
@pytest.mark.parametrize(
    "external_doctype", [False, True], ids=["internal", "external"]
)
@pytest.mark.parametrize(
    "declarations",
    [
        pytest.param('<!ENTITY text "custom">', id="internal-entity"),
        pytest.param(
            '<!ENTITY a "text"><!ENTITY text "&a;&a;&a;">', id="nested-entities"
        ),
        pytest.param('<!ENTITY % text "custom">', id="parameter-entity"),
    ],
)
def test_staged_svg_rejects_entity_declarations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: ConversionMode,
    external_doctype: bool,
    declarations: str,
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    identifier = ' SYSTEM "unused.dtd"' if external_doctype else ""
    document = (
        f"<!DOCTYPE svg{identifier} [{declarations}]>"
        '<svg xmlns="http://www.w3.org/2000/svg"/>'
    ).encode()
    stage_svg_document(monkeypatch, document)

    with pytest.raises(ConversionError, match="entity declarations"):
        convert_file(source, mode=mode)

    assert not source.with_suffix(".svg").exists()
    assert not list(tmp_path.glob(".sample-*.svg.tmp"))


@pytest.mark.parametrize("mode", ["embed", "vectorize"])
@pytest.mark.parametrize("resource_type", ["file", "network"])
@pytest.mark.parametrize(
    "reference_type", ["entity", "doctype", "unresolved", "attribute", "parameter"]
)
def test_staged_svg_never_accesses_external_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: ConversionMode,
    resource_type: str,
    reference_type: str,
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    resource = tmp_path / "private.txt"
    resource.write_text("Private resource", encoding="utf-8")
    identifier = (
        resource.as_uri() if resource_type == "file" else "http://127.0.0.1:9/svg.dtd"
    )
    if reference_type == "entity":
        declaration = f'<!DOCTYPE svg [<!ENTITY external SYSTEM "{identifier}">]>'
        content = "&external;"
    else:
        declaration = f'<!DOCTYPE svg SYSTEM "{identifier}">'
        content = "&external;" if reference_type == "unresolved" else ""
    if reference_type == "parameter":
        declaration = f'<!DOCTYPE svg SYSTEM "{identifier}" [%external;]>'
    attribute = ' title="&external;"' if reference_type == "attribute" else ""
    document = (
        f'{declaration}<svg xmlns="http://www.w3.org/2000/svg"{attribute}>'
        f"{content}</svg>"
    ).encode()
    stage_svg_document(monkeypatch, document)
    accesses: list[str] = []
    original_open = io.open
    original_path_open = Path.open

    def check_resource(file: object) -> None:
        """Record forbidden resource reads."""

        if str(file) == str(resource):
            accesses.append("file")
            raise OSError("Forbidden resource read")

    def observe_open(file: object, *args: object, **kwargs: object) -> object:
        """Observe direct file opens."""

        check_resource(file)
        return original_open(file, *args, **kwargs)

    def observe_path_open(file: Path, *args: object, **kwargs: object) -> object:
        """Observe path file opens."""

        check_resource(file)
        return original_path_open(file, *args, **kwargs)

    def observe_connect(_socket: socket.socket, _address: object) -> None:
        """Record forbidden network connections."""

        accesses.append("network")
        raise OSError("Forbidden network connection")

    monkeypatch.setattr(io, "open", observe_open)
    monkeypatch.setattr(builtins, "open", observe_open)
    monkeypatch.setattr(Path, "open", observe_path_open)
    monkeypatch.setattr(socket.socket, "connect", observe_connect)
    with pytest.raises(OSError, match="Forbidden resource read"):
        resource.read_text(encoding="utf-8")
    open_through_io = io.open
    with pytest.raises(OSError, match="Forbidden resource read"):
        open_through_io(resource)
    with pytest.raises(OSError, match="Forbidden resource read"):
        builtins.open(resource)
    with socket.socket() as connection:
        with pytest.raises(OSError, match="Forbidden network connection"):
            connection.connect(("127.0.0.1", 9))
    assert accesses == ["file", "file", "file", "network"]
    accesses.clear()

    if reference_type == "doctype":
        output = convert_file(source, mode=mode)
        assert output.read_bytes() == document
    else:
        with pytest.raises(ConversionError, match="entit"):
            convert_file(source, mode=mode)
        assert not source.with_suffix(".svg").exists()

    assert accesses == []
    assert not list(tmp_path.glob(".sample-*.svg.tmp"))


def test_successful_conversion_replaces_destination_after_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")
    destination = tmp_path / "result.svg"
    destination.write_text("original", encoding="utf-8")
    replace_calls: list[tuple[Path, Path]] = []
    real_replace = converter_module.os.replace

    def observe_replace(source_path: Path, destination_path: Path) -> None:
        staged_document = source_path.read_text(encoding="utf-8")
        assert staged_document
        assert destination_path.read_text(encoding="utf-8") == "original"
        replace_calls.append((source_path, destination_path))
        real_replace(source_path, destination_path)

    monkeypatch.setattr(converter_module.os, "replace", observe_replace)

    output = convert_file(source, destination, overwrite=True)

    assert output == destination
    assert len(replace_calls) == 1
    assert replace_calls[0][1] == destination
    assert replace_calls[0][0].name.startswith(".result-")
    assert replace_calls[0][0].name.endswith(".svg.tmp")
    assert "data:image/png;base64," in destination.read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".result-*.svg.tmp"))


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


def test_oversized_image_raises_conversion_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)
    source = create_image(tmp_path / "huge.png", "PNG", (6, 6))

    with pytest.raises(ConversionError, match="exceeds the safe pixel limit"):
        convert_file(source)

    assert not (tmp_path / "huge.svg").exists()


def test_oversized_image_is_reported_without_stopping_the_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)
    source_directory = tmp_path / "images"
    create_image(source_directory / "a-huge.png", "PNG", (6, 6))
    create_image(source_directory / "b-small.png", "PNG", (2, 2))

    result = convert_directory(source_directory)

    assert [path.name for path in result.converted] == ["b-small.svg"]
    assert [failure.input_path.name for failure in result.failed] == ["a-huge.png"]
    assert isinstance(result.failed[0].error, ConversionError)


def test_oversized_image_cannot_bypass_the_limit_when_optimizing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = create_image(tmp_path / "huge.png", "PNG", (6, 6))
    real_read_metadata = embed_module._read_image_metadata

    def read_metadata_then_lower_limit(path: Path) -> tuple[int, int, str]:
        metadata = real_read_metadata(path)
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)
        return metadata

    monkeypatch.setattr(
        embed_module, "_read_image_metadata", read_metadata_then_lower_limit
    )

    options = EmbedOptions(max_width=3)
    with pytest.raises(ConversionError, match="exceeds the safe pixel limit"):
        convert_file(source, embed_options=options)


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
    options = EmbedOptions(max_width=100)

    with pytest.raises(ValueError, match="embed_options can only"):
        convert_file(source, mode="vectorize", embed_options=options)


def test_vectorize_mode_explains_missing_optional_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = create_image(tmp_path / "sample.png", "PNG")

    def raise_missing_module(_: str) -> object:
        raise ModuleNotFoundError("No module named 'vtracer'")

    monkeypatch.setattr(
        vectorize_module.importlib, "import_module", raise_missing_module
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


@pytest.mark.parametrize(
    ("embed_options", "expected_size"),
    [
        pytest.param(None, (3, 2), id="default"),
        pytest.param(EmbedOptions(max_width=2), (2, 1), id="resize"),
        pytest.param(
            EmbedOptions(png_compress_level=9, optimize_png=True),
            (3, 2),
            id="png-options",
        ),
    ],
)
def test_tiff_avoids_read_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    embed_options: EmbedOptions | None,
    expected_size: tuple[int, int],
) -> None:
    source = create_image(tmp_path / "scan.tiff", "TIFF")
    original_read_bytes = Path.read_bytes

    def tiff_avoids_read_bytes(input_path: Path) -> bytes:
        """Reject eager TIFF reads."""

        if input_path == source:
            raise AssertionError("Unexpected read_bytes() call for TIFF input")
        return original_read_bytes(input_path)

    monkeypatch.setattr(Path, "read_bytes", tiff_avoids_read_bytes)
    metric = convert_file_with_metrics(source, embed_options=embed_options)

    assert metric.input_bytes == source.stat().st_size

    with Image.open(BytesIO(embedded_raster_bytes(metric.output_path))) as png:
        assert png.format == "PNG"
        assert png.size == expected_size


def test_tiff_reencoding_applies_exif_orientation(tmp_path: Path) -> None:
    source = tmp_path / "rotated.tiff"
    image = Image.new("RGB", (6, 4), color=(25, 50, 75))
    image.putpixel((0, 0), (255, 0, 0))
    image.putpixel((5, 3), (0, 255, 0))
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = 6
    image.save(source, format="TIFF", exif=exif)

    output = convert_file(source)

    with Image.open(BytesIO(embedded_raster_bytes(output))) as png:
        assert png.format == "PNG"
        assert png.size == (4, 6)
        assert png.getpixel((3, 0)) == (255, 0, 0)
        assert png.getpixel((0, 5)) == (0, 255, 0)
        assert ExifTags.Base.Orientation not in png.getexif()


def test_tiff_transcoding_passes_png_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = create_image(tmp_path / "scan.tiff", "TIFF")
    original_save = Image.Image.save
    save_calls: list[dict[str, object]] = []

    def observe_save(
        image: Image.Image, destination: BytesIO, **save_kwargs: object
    ) -> None:
        """Record real image saves."""

        save_calls.append(save_kwargs)
        original_save(image, destination, **save_kwargs)

    monkeypatch.setattr(Image.Image, "save", observe_save)
    output = convert_file(
        source, embed_options=EmbedOptions(png_compress_level=9, optimize_png=True)
    )

    assert len(save_calls) == 1
    assert save_calls[0]["format"] == "PNG"
    assert save_calls[0]["compress_level"] == 9
    assert save_calls[0]["optimize"] is True
    with Image.open(BytesIO(embedded_raster_bytes(output))) as png:
        assert png.format == "PNG"
        assert png.size == (3, 2)
        assert png.getpixel((0, 0)) == (25, 50, 75)
