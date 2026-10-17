from pathlib import Path
from xml.etree import ElementTree

import pytest
from PIL import Image

from svgconverter import VectorizeOptions, convert_file_with_metrics
from svgconverter.cli import main

SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20">
    <defs>
        <linearGradient id="paint">
            <stop offset="0" stop-color="red"/>
            <stop offset="1" stop-color="blue" stop-opacity="0.5"/>
        </linearGradient>
    </defs>
    <g opacity="0.75" transform="translate(1 1)">
        <path d="M0 0 L18 0 L18 18 Z" fill="url(#paint)"/>
    </g>
    <text x="2" y="10" xml:space="preserve"> a <tspan> b </tspan> c </text>
</svg>
"""


def fake_vectorizer(monkeypatch: pytest.MonkeyPatch) -> None:
    def write_svg(source: Path, destination: Path, options: VectorizeOptions) -> None:
        destination.write_text(SVG, encoding="utf-8")

    monkeypatch.setattr("svgconverter.converter.vectorize_image", write_svg)


def test_opt_in_minifies_markup_preserving_geometry_and_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_vectorizer(monkeypatch)
    source = tmp_path / "logo.png"
    Image.new("RGB", (20, 20)).save(source)
    original = convert_file_with_metrics(
        source, tmp_path / "plain.svg", mode="vectorize"
    )
    optimized = convert_file_with_metrics(
        source,
        tmp_path / "small.svg",
        mode="vectorize",
        vectorize_options=VectorizeOptions(optimize_svg=True),
    )

    assert original.output_path.read_text() == SVG
    assert optimized.svg_bytes == optimized.output_path.stat().st_size
    assert optimized.svg_bytes < original.svg_bytes
    before = ElementTree.fromstring(SVG)
    after = ElementTree.parse(optimized.output_path).getroot()
    before.find(".//{http://www.w3.org/2000/svg}path").set("d", "M0 0L18 0L18 18Z")
    assert [(n.tag, n.attrib) for n in after.iter()] == [
        (n.tag, n.attrib) for n in before.iter()
    ]
    ns = {"s": "http://www.w3.org/2000/svg"}
    assert "".join(after.find("s:text", ns).itertext()) == " a  b  c "


def test_cli_optimization_is_explicit_and_vectorize_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_vectorizer(monkeypatch)
    source = tmp_path / "logo.png"
    Image.new("RGB", (20, 20)).save(source)
    assert main([str(source), "--mode", "vectorize", "--optimize-svg"]) == 0
    assert source.with_suffix(".svg").stat().st_size < len(SVG.encode())
    with pytest.raises(SystemExit) as error:
        main([str(source), "--optimize-svg"])
    assert error.value.code == 2
    assert "vectorize" in capsys.readouterr().err


def test_optimization_failure_preserves_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from svgconverter import ConversionError

    fake_vectorizer(monkeypatch)
    source = tmp_path / "logo.png"
    Image.new("RGB", (20, 20)).save(source)
    destination = source.with_suffix(".svg")
    destination.write_text("existing SVG")

    def fail(path: Path) -> None:
        raise ConversionError("Cannot optimize SVG")

    monkeypatch.setattr("svgconverter.converter.optimize_svg_file", fail)
    with pytest.raises(ConversionError, match="optimize"):
        convert_file_with_metrics(
            source,
            overwrite=True,
            mode="vectorize",
            vectorize_options=VectorizeOptions(optimize_svg=True),
        )
    assert destination.read_text() == "existing SVG"
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("drawing", ["icon", "logo", "illustration"])
def test_generated_artwork_has_identical_rendering_after_optimization(
    tmp_path: Path, drawing: str
) -> None:
    pytest.importorskip("vtracer")
    renderer = pytest.importorskip("resvg_py")
    from PIL import ImageDraw

    source = tmp_path / "art.png"
    image = Image.new("RGB", (64, 64), "white")
    canvas = ImageDraw.Draw(image)
    if drawing == "icon":
        canvas.rectangle((8, 8, 56, 56), fill="black")
    elif drawing == "logo":
        canvas.ellipse((4, 4, 44, 44), fill="red")
        canvas.polygon([(24, 4), (60, 60), (4, 60)], fill="blue")
    else:
        for x in range(64):
            canvas.line((x, 0, x, 63), fill=(x * 4, 128, 255 - x * 4))
        canvas.ellipse((8, 8, 56, 56), fill="orange")
    image.save(source)
    plain = convert_file_with_metrics(source, tmp_path / "plain.svg", mode="vectorize")
    compact = convert_file_with_metrics(
        source,
        tmp_path / "compact.svg",
        mode="vectorize",
        vectorize_options=VectorizeOptions(optimize_svg=True),
    )
    assert compact.svg_bytes < plain.svg_bytes
    assert renderer.svg_to_bytes(svg_path=str(plain.output_path)) == (
        renderer.svg_to_bytes(svg_path=str(compact.output_path))
    )
