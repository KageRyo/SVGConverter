"""Export a bounded preview PNG through the standalone application launcher."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile

from ._publication import publish_without_overwrite
from .errors import SVGConverterError
from .paths import ensure_within_root, resolve_allowed_root
from .preview_process import create_preview


def _publish_png(
    destination: Path, png: bytes, *, allowed_root: Path | None = None
) -> None:
    destination = ensure_within_root(
        destination, allowed_root, label="Preview output path"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged: Path | None = None
    try:
        with NamedTemporaryFile(
            prefix=".svgconverter-preview-",
            suffix=".png.tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            staged = Path(temporary.name)
            temporary.write(png)
        publish_without_overwrite(staged, destination)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Export a static PNG thumbnail without writing a final SVG."""

    parser = argparse.ArgumentParser(
        prog="SVGConverter --preview",
        description=(
            "Render a static preview PNG, bounded to 360 pixels per side. "
            "Runs conversion and rendering in a separate process; does not save an SVG."
        ),
    )
    parser.add_argument("input", type=Path, help="One supported raster image")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New preview .png path; existing files are never replaced",
    )
    parser.add_argument("--mode", choices=("embed", "vectorize"), default="embed")
    parser.add_argument(
        "--allowed-root",
        type=Path,
        help="Restrict source and PNG output paths when called by an untrusted wrapper",
    )
    arguments = parser.parse_args(argv)
    if arguments.output.suffix.lower() != ".png":
        parser.error("--output must name a PNG file ending in .png")
    try:
        path_root = resolve_allowed_root(arguments.allowed_root)
        source = ensure_within_root(arguments.input, path_root, label="Input path")
        destination = ensure_within_root(
            arguments.output, path_root, label="Preview output path"
        )
        if source.resolve() == destination.resolve():
            parser.error("Preview output must differ from the source image")
        if destination.exists():
            parser.exit(1, f"error: Output already exists: {destination}\n")
        result = create_preview(source, mode=arguments.mode)
        _publish_png(destination, result.rendered_png, allowed_root=path_root)
    except (SVGConverterError, OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"error: {error}\n")
    print(f"Preview PNG: {destination}")
    return 0


if __name__ == "__main__":
    from multiprocessing import freeze_support

    freeze_support()
    raise SystemExit(main())
