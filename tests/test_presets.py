from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import svgconverter
import svgconverter.vectorize as vectorize_module
from svgconverter import VectorizeOptions
from svgconverter.cli import main


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (
            "default",
            {"colormode": "color", "hierarchical": "stacked", "mode": "spline"},
        ),
        (
            "logo",
            {
                "colormode": "color",
                "hierarchical": "stacked",
                "mode": "spline",
                "filter_speckle": 4,
                "color_precision": 8,
                "layer_difference": 16,
                "path_precision": 3,
            },
        ),
        (
            "icon",
            {
                "colormode": "color",
                "hierarchical": "cutout",
                "mode": "polygon",
                "filter_speckle": 2,
                "color_precision": 8,
                "layer_difference": 8,
                "path_precision": 2,
            },
        ),
        (
            "line-art",
            {
                "colormode": "binary",
                "hierarchical": "stacked",
                "mode": "spline",
                "filter_speckle": 2,
                "path_precision": 3,
            },
        ),
        (
            "illustration",
            {
                "colormode": "color",
                "hierarchical": "stacked",
                "mode": "spline",
                "filter_speckle": 4,
                "color_precision": 6,
                "layer_difference": 16,
                "path_precision": 3,
            },
        ),
    ],
)
def test_named_presets_map_to_explicit_backend_options(
    name: str, expected: dict[str, str | int]
) -> None:
    assert svgconverter.vectorize_preset(name).as_vtracer_kwargs() == expected


def test_default_preset_keeps_existing_options_and_manual_overrides_are_isolated() -> (
    None
):
    assert svgconverter.vectorize_preset() == VectorizeOptions()

    manual = svgconverter.vectorize_preset(
        "icon",
        hierarchical="stacked",
        curve_mode="spline",
        filter_speckle=0,
        color_precision=None,
    )

    assert manual == VectorizeOptions(
        hierarchical="stacked",
        curve_mode="spline",
        filter_speckle=0,
        layer_difference=8,
        path_precision=2,
    )
    assert svgconverter.vectorize_preset("icon").color_precision == 8
    assert svgconverter.vectorize_preset("icon").filter_speckle == 2


def test_unknown_preset_raises_clear_value_error() -> None:
    with pytest.raises(ValueError, match="photograph"):
        svgconverter.vectorize_preset("photograph")


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ([], VectorizeOptions()),
        (["--vectorize-color-mode", "binary"], VectorizeOptions(color_mode="binary")),
        (
            ["--vectorize-preset", "icon"],
            VectorizeOptions(
                hierarchical="cutout",
                curve_mode="polygon",
                filter_speckle=2,
                color_precision=8,
                layer_difference=8,
                path_precision=2,
            ),
        ),
        (
            ["--vectorize-preset", "line-art", "--vectorize-color-mode", "color"],
            VectorizeOptions(filter_speckle=2, path_precision=3),
        ),
        (
            [
                "--vectorize-preset",
                "icon",
                "--vectorize-hierarchical",
                "stacked",
                "--vectorize-curve-mode",
                "spline",
                "--filter-speckle",
                "0",
                "--color-precision",
                "7",
                "--layer-difference",
                "3",
                "--path-precision",
                "5",
            ],
            VectorizeOptions(
                filter_speckle=0,
                color_precision=7,
                layer_difference=3,
                path_precision=5,
            ),
        ),
    ],
    ids=["old-default", "old-manual", "preset", "explicit-color", "manual-overrides"],
)
def test_cli_applies_preset_then_explicit_manual_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    expected: VectorizeOptions,
) -> None:
    source = tmp_path / "logo.png"
    Image.new("RGB", (8, 8), "black").save(source)
    captured: dict[str, object] = {}

    def trace(_source: str, output: str, **options: object) -> None:
        captured.update(options)
        Path(output).write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h8v8z"/></svg>',
            encoding="utf-8",
        )

    monkeypatch.setattr(
        vectorize_module,
        "_load_vtracer",
        lambda: SimpleNamespace(convert_image_to_svg_py=trace),
    )

    assert main([str(source), "--mode", "vectorize", *arguments]) == 0
    assert captured == expected.as_vtracer_kwargs()
    assert source.with_suffix(".svg").is_file()


def test_cli_rejects_unknown_preset_with_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        main(["logo.png", "--mode", "vectorize", "--vectorize-preset", "photograph"])

    assert error.value.code == 2
    message = capsys.readouterr().err
    assert "photograph" in message
    assert "line-art" in message
