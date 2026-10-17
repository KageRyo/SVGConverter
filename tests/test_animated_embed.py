from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from queue import Queue
from threading import Event

import pytest
from PIL import Image

from svgconverter import ConversionError, EmbedOptions, convert_file, convert_paths
from svgconverter.cli import main
from svgconverter.gui import (
    GuiConversionOptions,
    SVGConverterApp,
    format_failure_details,
)


@pytest.fixture(params=[(".png", "PNG"), (".webp", "WEBP")], ids=["apng", "webp"])
def animated_source(tmp_path: Path, request: pytest.FixtureRequest) -> Path:
    suffix, image_format = request.param
    source = tmp_path / f"animated{suffix}"
    frames = [
        Image.new("RGBA", (40, 20), (255, 0, 0, 255)),
        Image.new("RGBA", (40, 20), (0, 0, 255, 128)),
    ]
    frames[0].save(
        source,
        format=image_format,
        save_all=True,
        append_images=frames[1:],
        duration=[80, 160],
        loop=3,
        lossless=True,
    )
    return source


@pytest.mark.parametrize(
    "options",
    [None, EmbedOptions(max_width=100, max_height=100), EmbedOptions(jpeg_quality=50)],
    ids=["default", "no-downscale", "irrelevant-jpeg-quality"],
)
def test_embed_preserves_animation_when_raster_bytes_need_no_changes(
    animated_source: Path, options: EmbedOptions | None
) -> None:
    output = convert_file(animated_source, embed_options=options)

    document = output.read_text(encoding="utf-8")
    encoded = document.split("base64,", maxsplit=1)[1].split('"', maxsplit=1)[0]
    embedded = base64.b64decode(encoded)
    assert embedded == animated_source.read_bytes()
    with Image.open(BytesIO(embedded)) as image:
        assert image.n_frames == 2
        assert image.info["loop"] == 3
        durations = []
        for frame in range(image.n_frames):
            image.seek(frame)
            image.load()
            durations.append(image.info["duration"])
        assert durations == [80, 160]


@pytest.mark.parametrize(
    "options",
    [EmbedOptions(max_width=20), EmbedOptions(max_height=10)],
    ids=["width", "height"],
)
def test_embed_rejects_animated_resizing_without_replacing_existing_output(
    animated_source: Path, options: EmbedOptions
) -> None:
    output = animated_source.with_suffix(".svg")
    output.write_bytes(b"existing output")

    with pytest.raises(ConversionError, match="animated.*resizing or re-encoding"):
        convert_file(animated_source, output, embed_options=options, overwrite=True)

    assert output.read_bytes() == b"existing output"
    assert not list(output.parent.glob(".*.svg.tmp"))


@pytest.mark.parametrize(
    "options",
    [EmbedOptions(png_compress_level=9), EmbedOptions(optimize_png=True)],
    ids=["compression", "optimization"],
)
def test_png_reencoding_rejects_apng_but_leaves_animated_webp_unchanged(
    animated_source: Path, options: EmbedOptions
) -> None:
    if animated_source.suffix == ".png":
        with pytest.raises(ConversionError, match="animated.*resizing or re-encoding"):
            convert_file(animated_source, embed_options=options)
        assert not animated_source.with_suffix(".svg").exists()
    else:
        output = convert_file(animated_source, embed_options=options)
        document = output.read_text(encoding="utf-8")
        encoded = document.split("base64,", maxsplit=1)[1].split('"', maxsplit=1)[0]
        assert base64.b64decode(encoded) == animated_source.read_bytes()


def test_batch_reports_animated_preprocessing_failure_and_converts_next_file(
    tmp_path: Path, animated_source: Path
) -> None:
    static_source = tmp_path / "static.png"
    Image.new("RGB", (40, 20), "green").save(static_source)
    output_dir = tmp_path / "out"

    result = convert_paths(
        [animated_source, static_source],
        output_dir,
        embed_options=EmbedOptions(max_width=20),
    )

    assert result.converted == (output_dir / "static.svg",)
    assert result.failure_count == 1
    assert result.failed[0].input_path == animated_source
    assert isinstance(result.failed[0].error, ConversionError)
    assert "animated" in str(result.failed[0].error)
    assert not (output_dir / "animated.svg").exists()
    assert not list(output_dir.glob(".*.svg.tmp"))


def test_cli_reports_animated_preprocessing_failure_and_nonzero_exit(
    animated_source: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as error:
        main([str(animated_source), "--max-width", "20"])

    assert error.value.code == 1
    assert "animated" in capsys.readouterr().err
    assert not animated_source.with_suffix(".svg").exists()


def test_gui_worker_reports_animated_preprocessing_as_per_file_failure(
    animated_source: Path,
) -> None:
    app = object.__new__(SVGConverterApp)
    app._events = Queue()
    app._cancel_event = Event()
    options = GuiConversionOptions(
        mode="embed",
        output_dir=None,
        overwrite=False,
        recursive=False,
        embed_options=EmbedOptions(max_width=20),
        vectorize_options=None,
    )

    app._run_conversion((str(animated_source),), options)

    event, progress = app._events.get_nowait()
    assert event == "progress"
    assert progress.failed == 1
    event, result = app._events.get_nowait()
    assert event == "done"
    assert result.success_count == 0
    assert result.failure_count == 1
    assert "animated" in format_failure_details(result)
    assert not animated_source.with_suffix(".svg").exists()
