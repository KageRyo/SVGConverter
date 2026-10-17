"""Optional VTracer integration for SVG path generation."""

from __future__ import annotations

import importlib
from pathlib import Path

from .errors import ConversionError, VectorizationDependencyError
from .models import VectorizeOptions


def _load_vtracer() -> object:
    try:
        return importlib.import_module("vtracer")
    except (ImportError, OSError) as error:
        raise VectorizationDependencyError(
            "Vectorize mode requires a working VTracer backend. "
            "For Python installs: pip install 'svgconverter[vectorize]'. "
            "For the standalone app, download the latest Windows executable. "
            f"Backend error: {error}"
        ) from error


def vectorize_image(
    source: Path, destination: Path, vectorize_options: VectorizeOptions
) -> None:
    """Trace a raster image into SVG paths using VTracer."""

    vtracer = _load_vtracer()
    try:
        vtracer.convert_image_to_svg_py(  # type: ignore[attr-defined]
            str(source), str(destination), **vectorize_options.as_vtracer_kwargs()
        )
    except Exception as error:
        raise ConversionError(f"Cannot vectorize image {source}: {error}") from error

    if not destination.is_file():
        raise ConversionError(f"Vectorization did not create an SVG: {destination}")
