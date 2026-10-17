"""Check native source/frozen GUI startup and real standalone conversions."""

from __future__ import annotations

import argparse
import os
import platform
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path
from xml.etree import ElementTree

SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def create_logo(path: Path) -> None:
    """Write a small high-contrast PNG using only the standard library."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack("!I", len(data))
            + kind
            + data
            + struct.pack("!I", zlib.crc32(kind + data))
        )

    rows = b"".join(
        b"\x00" + bytes(0 if 8 <= x < 24 and 8 <= y < 24 else 255 for x in range(32))
        for y in range(32)
    )
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack("!2I5B", 32, 32, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def validate_svg(path: Path, mode: str) -> None:
    root = ElementTree.parse(path).getroot()
    if root.tag != f"{{{SVG_NAMESPACE}}}svg":
        raise RuntimeError(f"{mode}: output is missing the SVG root/namespace")
    images = list(root.iter(f"{{{SVG_NAMESPACE}}}image"))
    paths = list(root.iter(f"{{{SVG_NAMESPACE}}}path"))
    if mode == "embed" and not images:
        raise RuntimeError("Embed output did not contain an image")
    if mode == "vectorize" and (
        images or not paths or not any(path.get("d", "").strip() for path in paths)
    ):
        raise RuntimeError("Vectorize output must contain real paths without images")


def check_gui_startup(
    command: list[str], environment: dict[str, str], working_directory: Path
) -> None:
    """Catch frozen startup crashes without leaving a desktop process running."""

    with subprocess.Popen(
        command,
        cwd=working_directory,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ) as process:
        try:
            output, _ = process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            print("Frozen GUI remained running after startup.")
        else:
            raise RuntimeError(
                f"Frozen GUI exited during startup ({process.returncode}): {output}"
            )
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--source", action="store_true")
    target.add_argument("--executable", type=Path)
    arguments = parser.parse_args()
    repository = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    for variable in ("PYTHONHOME", "PYTHONPATH"):
        environment.pop(variable, None)
    environment["PYTHONNOUSERSITE"] = "1"
    if arguments.source:
        command = [sys.executable, str(repository / "main.py")]
    else:
        command = [str(arguments.executable.resolve(strict=True))]
        # Frozen conversions must not discover the build interpreter or packages.
        environment["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
        for variable in (
            "LD_LIBRARY_PATH",
            "DYLD_LIBRARY_PATH",
            "DYLD_FALLBACK_LIBRARY_PATH",
        ):
            environment.pop(variable, None)
    print(f"Native evaluation: {platform.system()} {platform.machine()}")
    with tempfile.TemporaryDirectory(prefix="svgconverter-native-") as directory:
        working_directory = Path(directory)
        source = working_directory / "logo spaces 漢字.png"
        create_logo(source)
        for mode in ("embed", "vectorize"):
            output = working_directory / f"{mode}.svg"
            result = subprocess.run(
                command
                + ["--cli", str(source), "--output", str(output), "--mode", mode],
                cwd=working_directory,
                env=environment,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if result.returncode:
                raise RuntimeError(
                    f"{mode} failed ({result.returncode}): {result.stderr}"
                )
            validate_svg(output, mode)
            print(f"{mode} conversion passed ({output.stat().st_size} bytes).")
        invalid_source = working_directory / "broken.png"
        invalid_source.write_bytes(b"This is not an image")
        failure_output = working_directory / "failure.svg"
        failure = subprocess.run(
            command + ["--cli", str(invalid_source), "--output", str(failure_output)],
            cwd=working_directory,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if failure.returncode != 1 or failure_output.exists():
            raise RuntimeError("Invalid-image conversion did not fail safely")
        if arguments.source:
            subprocess.run(
                [
                    sys.executable,
                    str(repository / ".github/scripts/probe-native-gui.py"),
                ],
                cwd=working_directory,
                env=environment,
                timeout=30,
                check=True,
            )
        else:
            check_gui_startup(command, environment, working_directory)


if __name__ == "__main__":
    main()
