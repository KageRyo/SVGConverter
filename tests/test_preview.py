from __future__ import annotations

import importlib
from io import BytesIO
from pathlib import Path
from threading import Event
from xml.etree import ElementTree

import pytest
from PIL import Image

from svgconverter import ConversionError, EmbedOptions, VectorizeOptions


def preview_module():
    return importlib.import_module("svgconverter.preview")


def create_image(path: Path, size: tuple[int, int] = (12, 8)) -> Path:
    Image.new("RGB", size, "red").save(path)
    return path


def test_preview_uses_private_output_and_returns_images_after_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = preview_module()
    source = create_image(tmp_path / "影像 空白.png")
    final = source.with_suffix(".svg")
    final.write_text("keep existing output", encoding="utf-8")
    temporary_paths: list[Path] = []
    original_convert = module.convert_file_with_metrics

    def record_conversion(input_path: Path, output_path: Path, **kwargs: object):
        temporary_paths.append(output_path)
        return original_convert(input_path, output_path, **kwargs)

    def fake_render(svg_path: Path, _size: tuple[int, int]) -> bytes:
        assert svg_path.exists()
        assert 'width="6" height="4"' in svg_path.read_text(encoding="utf-8")
        with BytesIO() as output:
            Image.new("RGBA", (6, 4), "red").save(output, format="PNG")
            return output.getvalue()

    monkeypatch.setattr(module, "_load_renderer", lambda: object())
    monkeypatch.setattr(
        module, "_render_svg", lambda _renderer, path, size: fake_render(path, size)
    )
    monkeypatch.setattr(module, "convert_file_with_metrics", record_conversion)

    result = module.create_preview(source, embed_options=EmbedOptions(max_width=6))

    assert result.input_path == source
    assert result.source_size == (12, 8)
    assert result.output_size == (6, 4)
    assert result.input_bytes == source.stat().st_size
    assert result.svg_bytes > 0
    assert result.embedded_raster_bytes is not None
    assert result.animated is False
    assert Image.open(BytesIO(result.source_png)).size == (12, 8)
    assert Image.open(BytesIO(result.rendered_png)).size == (6, 4)
    assert final.read_text(encoding="utf-8") == "keep existing output"
    assert len(temporary_paths) == 1
    assert not temporary_paths[0].parent.exists()
    assert {path.name for path in tmp_path.iterdir()} == {final.name, source.name}


@pytest.mark.parametrize("failure_stage", ["conversion", "rendering", "cancellation"])
def test_preview_cleans_temporary_files_on_failure_and_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_stage: str
) -> None:
    module = preview_module()
    source = create_image(tmp_path / "source.png")
    cancel = Event()
    paths: list[Path] = []
    original_convert = module.convert_file_with_metrics

    def convert(input_path: Path, output_path: Path, **kwargs: object):
        paths.append(output_path)
        if failure_stage == "conversion":
            output_path.write_text("partial", encoding="utf-8")
            raise ConversionError("failed conversion")
        metric = original_convert(input_path, output_path, **kwargs)
        if failure_stage == "cancellation":
            cancel.set()
        return metric

    def render(*_args: object):
        raise ValueError("failed rendering")

    monkeypatch.setattr(module, "_load_renderer", lambda: object())
    monkeypatch.setattr(module, "convert_file_with_metrics", convert)
    monkeypatch.setattr(module, "_render_svg", render)
    expected = (
        module.PreviewCancelled
        if failure_stage == "cancellation"
        else module.PreviewError
    )

    with pytest.raises(expected):
        module.create_preview(source, should_cancel=cancel.is_set)

    assert paths
    assert not paths[0].parent.exists()
    assert not source.with_suffix(".svg").exists()


def test_preview_missing_renderer_has_install_hint_without_writing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = preview_module()
    source = create_image(tmp_path / "source.png")
    original_import = module.importlib.import_module

    def missing_renderer(name: str):
        if name == "resvg_py":
            raise ModuleNotFoundError("resvg_py")
        return original_import(name)

    monkeypatch.setattr(module.importlib, "import_module", missing_renderer)

    with pytest.raises(module.PreviewDependencyError, match=r"svgconverter\[preview\]"):
        module.create_preview(source)

    assert list(tmp_path.iterdir()) == [source]


def test_preview_reports_missing_vectorize_backend_and_cleans_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = preview_module()
    vectorize_module = importlib.import_module("svgconverter.vectorize")
    source = create_image(tmp_path / "source.png")
    monkeypatch.setattr(module, "_load_renderer", lambda: object())
    original_import = vectorize_module.importlib.import_module

    def missing_backend(name: str):
        if name == "vtracer":
            raise ModuleNotFoundError("vtracer")
        return original_import(name)

    monkeypatch.setattr(vectorize_module.importlib, "import_module", missing_backend)

    options = VectorizeOptions()
    with pytest.raises(module.PreviewError, match=r"svgconverter\[vectorize\]"):
        module.create_preview(source, mode="vectorize", vectorize_options=options)

    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize("mode", ["embed", "vectorize"])
def test_real_preview_renders_conversion_and_preserves_actual_size_metrics(
    tmp_path: Path, mode: str
) -> None:
    pytest.importorskip("resvg_py")
    if mode == "vectorize":
        pytest.importorskip("vtracer")
    module = preview_module()
    source = create_image(tmp_path / "logo.png", (24, 16))

    result = module.create_preview(source, mode=mode, thumbnail_size=(10, 10))

    assert result.source_size == (24, 16)
    assert result.output_size == (24, 16)
    assert result.mode == mode
    assert result.input_bytes == source.stat().st_size
    assert result.svg_bytes > 0
    if mode == "embed":
        assert result.embedded_raster_bytes == source.stat().st_size
    else:
        assert result.embedded_raster_bytes is None
    for data in (result.source_png, result.rendered_png):
        with Image.open(BytesIO(data)) as image:
            assert image.width <= 10
            assert image.height <= 10
            red, green, blue, alpha = image.convert("RGBA").getpixel(
                (image.width // 2, image.height // 2)
            )
            assert red > 200
            assert green < 30
            assert blue < 30
            assert alpha == 255
    assert not source.with_suffix(".svg").exists()


@pytest.mark.parametrize("max_height", [None, 20])
def test_real_embed_preview_normalizes_rendered_payload_exif_and_resizing(
    tmp_path: Path,
    max_height: int | None,
) -> None:
    pytest.importorskip("resvg_py")
    module = preview_module()
    source = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (40, 20), "red")
    for x in range(20, 40):
        for y in range(20):
            image.putpixel((x, y), (0, 0, 255))
    exif = image.getexif()
    exif[274] = 6
    image.save(source, exif=exif, quality=100, subsampling=0)

    result = module.create_preview(
        source, embed_options=EmbedOptions(max_height=max_height)
    )

    assert result.source_size == (20, 40)
    assert result.output_size == ((10, 20) if max_height else (20, 40))
    for data in (result.source_png, result.rendered_png):
        with Image.open(BytesIO(data)) as preview:
            assert preview.height == 2 * preview.width
            top = preview.convert("RGB").getpixel((preview.width // 2, 1))
            bottom = preview.convert("RGB").getpixel(
                (preview.width // 2, preview.height - 2)
            )
            assert top[0] > top[2]
            assert bottom[2] > bottom[0]


def test_render_adapter_uses_embedded_payload_and_leaves_svg_unchanged(
    tmp_path: Path,
) -> None:
    pytest.importorskip("resvg_py")
    module = preview_module()
    source = create_image(tmp_path / "source.bmp")
    from svgconverter import convert_file

    output = convert_file(source)
    original = output.read_bytes()

    rendered = module._render_svg(module._load_renderer(), output, (12, 8))

    assert output.read_bytes() == original
    assert (
        ElementTree.fromstring(original).find("{http://www.w3.org/2000/svg}image")
        is not None
    )
    with Image.open(BytesIO(rendered)) as image:
        assert image.convert("RGB").getpixel((5, 5)) == (255, 0, 0)
