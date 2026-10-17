"""Isolated, bounded conversion previews without a Tkinter dependency."""

from __future__ import annotations

import base64
import importlib
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

from PIL import Image, ImageOps

from .converter import convert_file_with_metrics
from .errors import SVGConverterError
from .models import ConversionMode, EmbedOptions, VectorizeOptions


class PreviewError(SVGConverterError):
    """A conversion or rendering failure while preparing a preview."""


class PreviewDependencyError(PreviewError):
    """The optional SVG renderer is unavailable."""


class PreviewCancelled(PreviewError):
    """A preview was cancelled at a safe stage boundary."""


@dataclass(frozen=True)
class PreviewResult:
    """Detached thumbnails and actual conversion sizes; no temporary paths."""

    input_path: Path
    mode: ConversionMode
    source_png: bytes
    rendered_png: bytes
    source_size: tuple[int, int]
    output_size: tuple[int, int]
    input_bytes: int
    svg_bytes: int
    embedded_raster_bytes: int | None
    animated: bool


def _load_renderer() -> object:
    try:
        return importlib.import_module("resvg_py")
    except (ImportError, OSError) as error:
        raise PreviewDependencyError(
            "Preview requires the optional SVG renderer. "
            "Install it with: pip install 'svgconverter[preview]'"
        ) from error


def _png_bytes(image: Image.Image) -> bytes:
    with BytesIO() as output:
        image.save(output, format="PNG")
        return output.getvalue()


def _source_thumbnail(
    source: Path, thumbnail_size: tuple[int, int]
) -> tuple[bytes, tuple[int, int], bool]:
    with Image.open(source) as image:
        animated = getattr(image, "n_frames", 1) > 1
        oriented = ImageOps.exif_transpose(image)
        source_size = oriented.size
        oriented.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
        return _png_bytes(oriented.convert("RGBA")), source_size, animated


def _svg_size(svg_path: Path) -> tuple[int, int]:
    root = ElementTree.parse(svg_path).getroot()
    return (
        int(float(root.attrib["width"].removesuffix("px"))),
        int(float(root.attrib["height"].removesuffix("px"))),
    )


def _render_svg(
    renderer: object, svg_path: Path, render_size: tuple[int, int]
) -> bytes:
    # resvg does not apply embedded JPEG EXIF orientation and does not decode
    # every browser-supported raster format. Normalize the *converted payload*
    # for rendering only, preserving resizing/compression and original SVG bytes.
    root = ElementTree.parse(svg_path).getroot()
    for element in root.iter("{http://www.w3.org/2000/svg}image"):
        href = element.get("href", "")
        if not href.startswith("data:image/"):
            continue
        _header, encoded = href.split(",", 1)
        with Image.open(BytesIO(base64.b64decode(encoded, validate=True))) as image:
            raster = ImageOps.exif_transpose(image).convert("RGBA")
            payload = base64.b64encode(_png_bytes(raster)).decode("ascii")
        element.set("href", f"data:image/png;base64,{payload}")
    return renderer.svg_to_bytes(  # type: ignore[attr-defined]
        svg_string=ElementTree.tostring(root, encoding="unicode"),
        width=render_size[0],
        height=render_size[1],
        skip_system_fonts=True,
    )


def _check_cancelled(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel is not None and should_cancel():
        raise PreviewCancelled("Preview cancelled.")


def create_preview(
    input_path: str | Path,
    *,
    mode: ConversionMode = "embed",
    embed_options: EmbedOptions | None = None,
    vectorize_options: VectorizeOptions | None = None,
    should_cancel: Callable[[], bool] | None = None,
    thumbnail_size: tuple[int, int] = (360, 360),
) -> PreviewResult:
    """Convert privately, render bounded thumbnails, and remove every temp file.

    Cancellation waits for the current conversion/render stage to finish. Only
    detached PNG bytes and metadata survive the temporary directory context.
    """

    if any(value <= 0 or value > 1024 for value in thumbnail_size):
        raise ValueError("Preview thumbnail dimensions must be between 1 and 1024.")
    _check_cancelled(should_cancel)
    renderer = _load_renderer()
    source = Path(input_path)
    try:
        source_png, source_size, animated = _source_thumbnail(source, thumbnail_size)
        _check_cancelled(should_cancel)
        with TemporaryDirectory(prefix="svgconverter-preview-") as directory:
            output = Path(directory) / "preview.svg"
            metric = convert_file_with_metrics(
                source,
                output,
                mode=mode,
                embed_options=embed_options,
                vectorize_options=vectorize_options,
            )
            _check_cancelled(should_cancel)
            output_size = _svg_size(output)
            scale = min(
                1.0,
                *(
                    bound / size
                    for bound, size in zip(thumbnail_size, output_size, strict=True)
                ),
            )
            render_size = tuple(max(1, round(size * scale)) for size in output_size)
            rendered_png = _render_svg(
                renderer, output, (render_size[0], render_size[1])
            )
            _check_cancelled(should_cancel)
            return PreviewResult(
                input_path=source,
                mode=mode,
                source_png=source_png,
                rendered_png=rendered_png,
                source_size=source_size,
                output_size=output_size,
                input_bytes=metric.input_bytes,
                svg_bytes=metric.svg_bytes,
                embedded_raster_bytes=metric.embedded_raster_bytes,
                animated=animated,
            )
    except PreviewCancelled:
        raise
    except Exception as error:
        raise PreviewError(str(error)) from error
