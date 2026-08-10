"""Core raster-image embedding functionality.

The conversion mode implemented here is deliberately named ``embed``: the
source raster bytes are Base64 encoded into an SVG ``<image>`` element. No
attempt is made to convert pixels into vector paths.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError

ConversionMode = Literal["embed"]

_SUPPORTED_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg"})
_MIME_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg"}


class SVGConverterError(Exception):
    """Base exception for expected SVGConverter failures."""


class InputPathError(SVGConverterError):
    """Raised when an input path is missing or is the wrong kind of path."""


class UnsupportedImageError(SVGConverterError):
    """Raised when an input is not a supported PNG or JPEG image."""


class OutputExistsError(SVGConverterError):
    """Raised when conversion would overwrite an existing SVG."""


class ConversionError(SVGConverterError):
    """Raised when an image cannot be read or an SVG cannot be written."""


@dataclass(frozen=True)
class ConversionFailure:
    """One failed item from a batch conversion."""

    input_path: Path
    error: SVGConverterError


@dataclass(frozen=True)
class BatchResult:
    """Successful and failed items from a directory conversion."""

    converted: tuple[Path, ...]
    failed: tuple[ConversionFailure, ...]

    @property
    def success_count(self) -> int:
        """Return the number of converted images."""

        return len(self.converted)

    @property
    def failure_count(self) -> int:
        """Return the number of files that could not be converted."""

        return len(self.failed)


def _validate_mode(mode: ConversionMode) -> None:
    if mode != "embed":
        raise ValueError(
            "Only mode='embed' is available; vectorization is not implemented."
        )


def _validate_input(input_path: Path) -> None:
    if not input_path.exists():
        raise InputPathError(f"Input file does not exist: {input_path}")
    if not input_path.is_file():
        raise InputPathError(f"Input path is not a file: {input_path}")
    if input_path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(_SUPPORTED_EXTENSIONS))
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
    except (OSError, UnidentifiedImageError) as error:
        raise ConversionError(f"Cannot read image {input_path}: {error}") from error


def _svg_document(*, data_uri: str, width: int, height: int) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        f'  <image href="{data_uri}" width="{width}" height="{height}"/>\n'
        "</svg>\n"
    )


def convert_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    overwrite: bool = False,
    mode: ConversionMode = "embed",
) -> Path:
    """Embed one PNG or JPEG image in an SVG file and return its output path.

    ``output_path`` defaults to the input filename with an ``.svg`` suffix.
    Parent directories for an explicit output path are created automatically.
    Existing outputs are preserved unless ``overwrite=True`` is provided.
    """

    _validate_mode(mode)
    source = Path(input_path)
    _validate_input(source)
    destination = (
        Path(output_path) if output_path is not None else source.with_suffix(".svg")
    )

    if destination.exists() and not overwrite:
        raise OutputExistsError(
            f"Output already exists: {destination}. Pass overwrite=True to replace it."
        )
    if destination.exists() and destination.is_dir():
        raise InputPathError(f"Output path is a directory: {destination}")

    width, height, mime_type = _read_image_metadata(source)
    try:
        image_data = source.read_bytes()
        data_uri = (
            f"data:{mime_type};base64,{base64.b64encode(image_data).decode('ascii')}"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            _svg_document(data_uri=data_uri, width=width, height=height),
            encoding="utf-8",
        )
    except OSError as error:
        raise ConversionError(f"Cannot write SVG {destination}: {error}") from error

    return destination


def convert_directory(
    directory: str | Path,
    output_dir: str | Path | None = None,
    *,
    overwrite: bool = False,
    mode: ConversionMode = "embed",
) -> BatchResult:
    """Convert supported images directly in a directory without recursing.

    Files with non-image extensions are ignored. Each supported image is
    attempted independently, so a corrupt image does not stop the batch.
    """

    _validate_mode(mode)
    source_directory = Path(directory)
    if not source_directory.exists():
        raise InputPathError(f"Input directory does not exist: {source_directory}")
    if not source_directory.is_dir():
        raise InputPathError(f"Input path is not a directory: {source_directory}")

    destination_directory = (
        Path(output_dir) if output_dir is not None else source_directory
    )
    converted: list[Path] = []
    failed: list[ConversionFailure] = []
    candidates = sorted(
        (
            path
            for path in source_directory.iterdir()
            if path.is_file() and path.suffix.lower() in _SUPPORTED_EXTENSIONS
        ),
        key=lambda path: path.name.casefold(),
    )

    for source in candidates:
        destination = destination_directory / f"{source.stem}.svg"
        try:
            converted.append(
                convert_file(source, destination, overwrite=overwrite, mode=mode)
            )
        except SVGConverterError as error:
            failed.append(ConversionFailure(input_path=source, error=error))

    return BatchResult(converted=tuple(converted), failed=tuple(failed))


class SVGConverter:
    """Configurable facade for repeated SVG embedding operations."""

    def __init__(
        self, *, overwrite: bool = False, mode: ConversionMode = "embed"
    ) -> None:
        _validate_mode(mode)
        self.overwrite = overwrite
        self.mode = mode

    def convert_file(
        self, input_path: str | Path, output_path: str | Path | None = None
    ) -> Path:
        """Convert one image using this instance's configuration."""

        return convert_file(
            input_path, output_path, overwrite=self.overwrite, mode=self.mode
        )

    def convert_directory(
        self, directory: str | Path, output_dir: str | Path | None = None
    ) -> BatchResult:
        """Convert one directory using this instance's configuration."""

        return convert_directory(
            directory, output_dir, overwrite=self.overwrite, mode=self.mode
        )
