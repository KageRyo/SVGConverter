"""Optional VTracer integration for SVG path generation."""

from __future__ import annotations

import importlib
from pathlib import Path

from .errors import ConversionError, VectorizationDependencyError
from .models import VectorizeOptions


def _load_vtracer() -> object:
    try:
        return importlib.import_module("vtracer")
    except ModuleNotFoundError as error:
        raise VectorizationDependencyError(
            "Vectorize mode requires the optional VTracer backend. "
            "Install it with: pip install 'svgconverter[vectorize]'"
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
