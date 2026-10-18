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


@pytest.mark.parametrize("outside", ["input", "output", "parent-traversal"])
def test_preview_allowed_root_rejects_escape_before_starting_process_or_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outside: str
) -> None:
    module = importlib.import_module("svgconverter.preview_cli")
    root = tmp_path / "workspace"
    root.mkdir()
    source = root / "source.png"
    source.write_bytes(b"unchanged source")
    output = root / "preview.png"
    if outside == "input":
        source = tmp_path / "outside.png"
        source.write_bytes(b"unchanged source")
    elif outside == "output":
        output = tmp_path / "outside" / "preview.png"
    else:
        output = root / ".." / "outside" / "preview.png"
    create = Mock()
    monkeypatch.setattr(module, "create_preview", create)

    with pytest.raises(SystemExit) as status:
        module.main([str(source), "--output", str(output), "--allowed-root", str(root)])

    assert status.value.code == 1
    create.assert_not_called()
    assert source.read_bytes() == b"unchanged source"
    assert not output.exists()
    assert not (tmp_path / "outside").exists()


@pytest.mark.parametrize("escape", ["source-symlink", "output-parent-symlink"])
def test_preview_allowed_root_rejects_symlink_escape_before_starting_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, escape: str
) -> None:
    module = importlib.import_module("svgconverter.preview_cli")
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    source = root / "source.png"
    source.write_bytes(b"unchanged source")
    output = root / "preview.png"
    try:
        if escape == "source-symlink":
            target = outside / "source.png"
            target.write_bytes(b"unchanged source")
            source.unlink()
            source.symlink_to(target)
        else:
            alias = root / "out"
            alias.symlink_to(outside, target_is_directory=True)
            output = alias / "preview.png"
    except OSError:
        pytest.skip("This host cannot create symlinks")
    create = Mock()
    monkeypatch.setattr(module, "create_preview", create)

    with pytest.raises(SystemExit) as status:
        module.main([str(source), "--output", str(output), "--allowed-root", str(root)])

    assert status.value.code == 1
    create.assert_not_called()
    assert source.read_bytes() == b"unchanged source"
    assert not output.exists()


def test_preview_allowed_root_accepts_absolute_paths_within_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("svgconverter.preview_cli")
    source = tmp_path / "source.png"
    source.write_bytes(b"unchanged source")
    output = tmp_path / "nested" / "preview.png"
    result = fake_result(source)
    monkeypatch.setattr(module, "create_preview", Mock(return_value=result))

    assert (
        module.main(
            [str(source), "--output", str(output), "--allowed-root", str(tmp_path)]
        )
        == 0
    )

    assert output.read_bytes() == result.rendered_png
    assert source.read_bytes() == b"unchanged source"


def test_preview_publisher_rejects_outside_root_before_creating_parent(
    tmp_path: Path,
) -> None:
    from svgconverter import InputPathError

    module = importlib.import_module("svgconverter.preview_cli")
    root = tmp_path / "workspace"
    root.mkdir()
    output = tmp_path / "outside" / "preview.png"

    with pytest.raises(InputPathError, match="within allowed root"):
        module._publish_png(output, b"png", allowed_root=root)

    assert not output.parent.exists()
