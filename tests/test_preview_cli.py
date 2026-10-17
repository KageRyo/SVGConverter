from __future__ import annotations

import importlib
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image

from svgconverter.preview import PreviewResult


def fake_result(source: Path) -> PreviewResult:
    output = BytesIO()
    Image.new("RGBA", (8, 6), "red").save(output, format="PNG")
    png = output.getvalue()
    return PreviewResult(
        source, "embed", png, png, (8, 6), (8, 6), 100, 200, 100, False
    )


def test_preview_command_exports_png_without_creating_svg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("svgconverter.preview_cli")
    source = tmp_path / "source.png"
    source.write_bytes(b"source untouched")
    output = tmp_path / "preview.png"
    result = fake_result(source)
    create = Mock(return_value=result)
    monkeypatch.setattr(module, "create_preview", create)

    assert module.main([str(source), "--output", str(output)]) == 0

    assert output.read_bytes() == result.rendered_png
    assert source.read_bytes() == b"source untouched"
    assert not source.with_suffix(".svg").exists()
    create.assert_called_once_with(source, mode="embed")


@pytest.mark.parametrize("destination", ["source", "existing", "svg"])
def test_preview_command_rejects_unsafe_destination_before_starting_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, destination: str
) -> None:
    module = importlib.import_module("svgconverter.preview_cli")
    source = tmp_path / "source.png"
    source.write_bytes(b"source untouched")
    output = source if destination == "source" else tmp_path / f"preview.{destination}"
    if destination == "existing":
        output = tmp_path / "existing.png"
        output.write_bytes(b"existing preview")
    create = Mock()
    monkeypatch.setattr(module, "create_preview", create)

    with pytest.raises(SystemExit) as status:
        module.main([str(source), "--output", str(output)])

    assert status.value.code == (1 if destination == "existing" else 2)
    create.assert_not_called()
    assert source.read_bytes() == b"source untouched"
    if destination == "existing":
        assert output.read_bytes() == b"existing preview"


def test_preview_command_exclusive_publication_preserves_concurrent_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("svgconverter.preview_cli")
    source = tmp_path / "source.png"
    source.write_bytes(b"source untouched")
    output = tmp_path / "preview.png"

    def concurrent_output(*_args, **_kwargs):
        output.write_bytes(b"created concurrently")
        return fake_result(source)

    monkeypatch.setattr(module, "create_preview", concurrent_output)

    with pytest.raises(SystemExit) as status:
        module.main([str(source), "--output", str(output)])

    assert status.value.code == 1
    assert output.read_bytes() == b"created concurrently"
    assert set(tmp_path.iterdir()) == {source, output}
