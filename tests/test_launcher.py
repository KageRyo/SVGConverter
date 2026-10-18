"""Exercise the same launcher that is frozen into the Windows executable."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

import pytest
from PIL import Image, ImageDraw


@pytest.mark.parametrize("mode", ["embed", "vectorize"])
def test_packaged_launcher_cli_converts_without_opening_gui(
    tmp_path: Path, mode: str
) -> None:
    if mode == "vectorize":
        pytest.importorskip("vtracer")
    source = tmp_path / "logo 空間.png"
    output = tmp_path / "logo 空間.svg"
    image = Image.new("RGB", (32, 32), "white")
    ImageDraw.Draw(image).rectangle((8, 8, 24, 24), fill="black")
    image.save(source)
    repository = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository / "src")
    # A CLI invocation must work even when no desktop display is available.
    environment.pop("DISPLAY", None)

    result = subprocess.run(
        [
            sys.executable,
            str(repository / "main.py"),
            "--cli",
            str(source),
            "--output",
            str(output),
            "--mode",
            mode,
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    document = ElementTree.parse(output)
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    expected = "path" if mode == "vectorize" else "image"
    assert document.findall(f".//svg:{expected}", namespace)
    if mode == "vectorize":
        assert not document.findall(".//svg:image", namespace)


def test_packaged_launcher_cli_preserves_failure_exit_code(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository / "src")
    environment.pop("DISPLAY", None)

    result = subprocess.run(
        [
            sys.executable,
            str(repository / "main.py"),
            "--cli",
            str(tmp_path / "missing"),
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 1
    assert "error:" in result.stderr
    assert "does not exist" in result.stderr


def test_packaged_launcher_opens_gui_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import runpy
    from unittest.mock import Mock

    import svgconverter.gui

    run_gui = Mock()
    monkeypatch.setattr(svgconverter.gui, "run_gui", run_gui)
    monkeypatch.setattr(sys, "argv", ["SVGConverter.exe"])
    repository = Path(__file__).resolve().parents[1]

    with pytest.raises(SystemExit) as exit_status:
        runpy.run_path(str(repository / "main.py"), run_name="__main__")

    assert exit_status.value.code == 0
    run_gui.assert_called_once_with()


@pytest.mark.parametrize("mode", ["embed", "vectorize"])
def test_packaged_launcher_exports_preview_through_spawned_process(
    tmp_path: Path, mode: str
) -> None:
    pytest.importorskip("resvg_py")
    if mode == "vectorize":
        pytest.importorskip("vtracer")
    source = tmp_path / "預覽 空間.png"
    output = tmp_path / "preview.png"
    final_svg = source.with_suffix(".svg")
    image = Image.new("RGB", (32, 24), "white")
    ImageDraw.Draw(image).rectangle((8, 8, 24, 20), fill="black")
    image.save(source)
    original_source = source.read_bytes()
    final_svg.write_text("existing SVG", encoding="utf-8")
    repository = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository / "src")
    environment.pop("DISPLAY", None)

    result = subprocess.run(
        [
            sys.executable,
            str(repository / "main.py"),
            "--preview",
            str(source),
            "--output",
            str(output),
            "--mode",
            mode,
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    with Image.open(output) as preview:
        assert preview.format == "PNG"
        assert preview.size == (32, 24)
        assert preview.convert("RGB").getpixel((16, 12)) == (0, 0, 0)
    assert source.read_bytes() == original_source
    assert final_svg.read_text(encoding="utf-8") == "existing SVG"
