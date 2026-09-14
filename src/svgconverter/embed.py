"""Raster validation, preprocessing, and SVG embedding."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from PIL import Image

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
            return image.width, image.height, mime_type
    except UnsupportedImageError:
        raise
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


def _embedded_raster(
    source: Path, embed_options: EmbedOptions | None
) -> tuple[bytes, int, int, str]:
    """Return source bytes or explicitly requested optimized raster bytes."""

    width, height, mime_type = _read_image_metadata(source)
    source_data = source.read_bytes()
    if embed_options is None or not embed_options.is_enabled:
        return source_data, width, height, mime_type

    try:
        with Image.open(source) as image:
            image_format = image.format
            if image_format is None:
                raise UnsupportedImageError(
                    f"Unsupported image format in {source}: unknown"
                )
            target_width, target_height = _target_dimensions(
                image.width, image.height, embed_options
            )
            should_resize = (target_width, target_height) != image.size
            should_reencode = (
                should_resize
                or (image_format == "JPEG" and embed_options.jpeg_quality is not None)
                or (
                    image_format == "PNG"
                    and (
                        embed_options.png_compress_level is not None
                        or embed_options.optimize_png
                    )
                )
            )
            if not should_reencode:
                return source_data, width, height, mime_type

            image.load()
            if should_resize:
                image = image.resize(
                    (target_width, target_height), Image.Resampling.LANCZOS
                )
            data = BytesIO()
            image.save(
                data,
                format=image_format,
                **_image_save_kwargs(image, image_format, embed_options),
            )
            return data.getvalue(), image.width, image.height, mime_type
    except UnsupportedImageError:
        raise
    except (OSError, ValueError) as error:
        raise ConversionError(f"Cannot optimize image {source}: {error}") from error


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
