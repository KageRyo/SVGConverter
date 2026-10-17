"""Named starting points for VTracer with explicit manual overrides."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

from .models import VectorizeOptions

VECTORIZE_PRESETS: Mapping[str, VectorizeOptions] = MappingProxyType(
    {
        "default": VectorizeOptions(),
        "logo": VectorizeOptions(
            filter_speckle=4,
            color_precision=8,
            layer_difference=16,
            path_precision=3,
        ),
        "icon": VectorizeOptions(
            hierarchical="cutout",
            curve_mode="polygon",
            filter_speckle=2,
            color_precision=8,
            layer_difference=8,
            path_precision=2,
        ),
        "line-art": VectorizeOptions(
            color_mode="binary", filter_speckle=2, path_precision=3
        ),
        "illustration": VectorizeOptions(
            filter_speckle=4,
            color_precision=6,
            layer_difference=16,
            path_precision=3,
        ),
    }
)


def vectorize_preset(name: str = "default", **overrides: object) -> VectorizeOptions:
    """Return a named preset, replacing any explicitly supplied option fields.

    The ``default`` preset is equivalent to ``VectorizeOptions()``. Overrides
    use the same field names as that dataclass; ``None`` resets an optional
    numeric setting to the backend default, and zero is preserved. Presets
    are starting points, not guarantees of fidelity for arbitrary images.
    """

    try:
        options = VECTORIZE_PRESETS[name]
    except KeyError as error:
        raise ValueError(
            f"Unknown vectorize preset {name!r}; "
            f"choose from: {', '.join(VECTORIZE_PRESETS)}."
        ) from error
    return replace(options, **overrides)


def preset_description(name: str, text: Mapping[str, str]) -> str:
    """Return the shared CLI/GUI description in the supplied translation."""

    return text[f"preset_{name.replace('-', '_')}_description"]
