"""Raster validation, preprocessing, and SVG embedding."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from PIL import ExifTags, Image, ImageOps

from .errors import ConversionError, InputPathError, UnsupportedImageError
from .models import EmbedOptions

SUPPORTED_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
)
_MIME_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
}
# EXIF orientations that rotate by 90 degrees, so displays swap width and height.
_TRANSPOSED_ORIENTATIONS = frozenset({5, 6, 7, 8})
# Browsers cannot display these formats inside an SVG <image>, so they are
# losslessly transcoded to PNG before embedding.
_PNG_TRANSCODED_FORMATS = frozenset({"TIFF"})
_PNG_MODES = frozenset({"1", "L", "LA", "I", "I;16", "P", "RGB", "RGBA"})
_ALPHA_MODES = frozenset({"La", "PA", "RGBa"})


def validate_input(input_path: Path) -> None:
    """Validate that ``input_path`` names a supported raster file."""

    if not input_path.exists():
        raise InputPathError(f"Input file does not exist: {input_path}")
    if not input_path.is_file():
        raise InputPathError(f"Input path is not a file: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedImageError(
            f"Unsupported image extension {input_path.suffix!r}; "
            f"supported extensions: {supported}"
        )


def _oversized_image_error(
    input_path: Path, error: Image.DecompressionBombError
) -> ConversionError:
    return ConversionError(
        f"Image {input_path} exceeds the safe pixel limit and was not decoded: {error}"
    )


def _display_size(image: Image.Image) -> tuple[int, int]:
    """Return the size viewers display after applying EXIF orientation."""

    orientation = image.getexif().get(ExifTags.Base.Orientation, 1)
    if orientation in _TRANSPOSED_ORIENTATIONS:
        return image.height, image.width
    return image.width, image.height


def _read_image_metadata(input_path: Path) -> tuple[int, int, str]:
    try:
        with Image.open(input_path) as image:
            image.verify()
        with Image.open(input_path) as image:
            mime_type = _MIME_TYPES.get(image.format or "")
            if mime_type is None:
                raise UnsupportedImageError(
                    f"Unsupported image format in {input_path}: "
                    f"{image.format or 'unknown'}"
                )
            width, height = _display_size(image)
            return width, height, mime_type
    except UnsupportedImageError:
        raise
    except Image.DecompressionBombError as error:
        raise _oversized_image_error(input_path, error) from error
    except OSError as error:
        raise ConversionError(f"Cannot read image {input_path}: {error}") from error


def _svg_document(*, data_uri: str, width: int, height: int) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        f'  <image href="{data_uri}" width="{width}" height="{height}"/>\n'
        "</svg>\n"
    )


def _target_dimensions(
    width: int, height: int, embed_options: EmbedOptions
) -> tuple[int, int]:
    """Return downscaled dimensions that honour every configured maximum."""

    scale_limits = [1.0]
    if embed_options.max_width is not None:
        scale_limits.append(embed_options.max_width / width)
    if embed_options.max_height is not None:
        scale_limits.append(embed_options.max_height / height)
    scale = min(scale_limits)
    return max(1, round(width * scale)), max(1, round(height * scale))


def _image_save_kwargs(
    image: Image.Image, image_format: str, embed_options: EmbedOptions
) -> dict[str, object]:
    """Return format-specific Pillow options for requested raster optimization."""

    save_kwargs: dict[str, object] = {}
    if icc_profile := image.info.get("icc_profile"):
        save_kwargs["icc_profile"] = icc_profile
    if exif := image.info.get("exif"):
        save_kwargs["exif"] = exif

    if image_format == "JPEG":
        if embed_options.jpeg_quality is None:
            save_kwargs["quality"] = 95
        else:
            save_kwargs["quality"] = embed_options.jpeg_quality
    elif image_format == "PNG":
        if embed_options.png_compress_level is not None:
            save_kwargs["compress_level"] = embed_options.png_compress_level
        if embed_options.optimize_png:
            save_kwargs["optimize"] = True
    return save_kwargs


def _png_compatible(image: Image.Image) -> Image.Image:
    """Return ``image`` in a pixel mode that PNG can store without loss."""

    if image.mode in _PNG_MODES:
        return image
    if image.mode.startswith("I;16"):
        return image.convert("I;16")
    converted = image.convert("RGBA" if image.mode in _ALPHA_MODES else "RGB")
    # A profile for the original colour space (for example CMYK) does not
    # describe the converted pixels.
    converted.info.pop("icc_profile", None)
    return converted


def _embedded_raster(
    source: Path, embed_options: EmbedOptions | None
) -> tuple[bytes, int, int, str]:
    """Return source bytes, or re-encoded bytes when requested or required.

    Formats that browsers cannot display are always re-encoded as PNG.
    """

    width, height, mime_type = _read_image_metadata(source)
    source_data = source.read_bytes()
    must_transcode = mime_type == _MIME_TYPES["TIFF"]
    if not must_transcode and (embed_options is None or not embed_options.is_enabled):
        return source_data, width, height, mime_type
    embed_options = embed_options or EmbedOptions()

    try:
        with Image.open(source) as image:
            image_format = image.format
            if image_format is None:
                raise UnsupportedImageError(
                    f"Unsupported image format in {source}: unknown"
                )
            output_format = (
                "PNG" if image_format in _PNG_TRANSCODED_FORMATS else image_format
            )
            target_width, target_height = _target_dimensions(
                width, height, embed_options
            )
            should_resize = (target_width, target_height) != (width, height)
            should_reencode = (
                should_resize
                or output_format != image_format
                or (image_format == "JPEG" and embed_options.jpeg_quality is not None)
                or (
                    output_format == "PNG"
                    and (
                        embed_options.png_compress_level is not None
                        or embed_options.optimize_png
                    )
                )
            )
            if not should_reencode:
                return source_data, width, height, mime_type

            image.load()
            # Bake EXIF orientation into the pixels so resizing uses the displayed
            # axes and the re-encoded raster cannot be rotated a second time.
            image = ImageOps.exif_transpose(image)
            if output_format == "PNG":
                image = _png_compatible(image)
            if should_resize:
                image = image.resize(
                    (target_width, target_height), Image.Resampling.LANCZOS
                )
            data = BytesIO()
            image.save(
                data,
                format=output_format,
                **_image_save_kwargs(image, output_format, embed_options),
            )
            return (
                data.getvalue(),
                image.width,
                image.height,
                _MIME_TYPES[output_format],
            )
    except UnsupportedImageError:
        raise
    except Image.DecompressionBombError as error:
        raise _oversized_image_error(source, error) from error
    except (OSError, ValueError) as error:
        raise ConversionError(f"Cannot re-encode image {source}: {error}") from error


def embed_image(
    source: Path, destination: Path, embed_options: EmbedOptions | None
) -> int:
    """Write an SVG containing the source raster as a data URI."""

    image_data, width, height, mime_type = _embedded_raster(source, embed_options)
    data_uri = f"data:{mime_type};base64,{base64.b64encode(image_data).decode('ascii')}"
    destination.write_text(
        _svg_document(data_uri=data_uri, width=width, height=height), encoding="utf-8"
    )
    return len(image_data)
