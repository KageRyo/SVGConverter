# SVGConverter

[正體中文](README_TW.md)

SVGConverter converts PNG, JPEG, WebP, BMP, and TIFF images to SVG through a
small Python API, command-line interface, and desktop GUI.

## Conversion modes

- **`embed`** (default) places the original raster bytes in an SVG `<image>`
  element. It preserves the source pixels, but it is not vectorization and can
  be larger than the original image because of Base64 encoding.
- **`vectorize`** traces raster regions into SVG paths using the optional
  [VTracer](https://github.com/visioncortex/vtracer) backend. It is most useful
  for logos, icons, illustrations, and high-contrast line art. Photographs can
  produce large, stylized output rather than a faithful smaller image.

## Installation

SVGConverter requires Python 3.10 or newer:

```bash
python -m pip install --upgrade svgconverter
```

Install vectorization support when needed:

```bash
python -m pip install --upgrade "svgconverter[vectorize]"
```

To run the current development version instead:

```bash
git clone https://github.com/KageRyo/SVGConverter.git
cd SVGConverter
python -m pip install .
```

## Command line

Convert one image, retaining its dimensions in the generated SVG:

```bash
svgconverter image.png
svgconverter photo.jpg --output output.svg
svgconverter logo.png --mode vectorize --vectorize-color-mode binary
```

Convert all supported images immediately inside a directory:

```bash
svgconverter ./images --output-dir ./svg-output
```

Include nested directories while retaining their relative paths under the
output directory:

```bash
svgconverter ./images --output-dir ./svg-output --recursive
```

Convert several explicit files in one batch. Shells that support glob expansion
can also expand patterns such as `./images/*.png` before invoking the command:

```bash
svgconverter image.png photo.jpg --output-dir ./svg-output
```

For batch conversion, existing output SVGs are skipped unless `--overwrite` is
supplied; the final summary reports converted, skipped, and failed items.
Supported inputs are PNG, JPG, JPEG, WebP, BMP, TIF, and TIFF (including
upper-case extensions). Run `svgconverter --help` for all options. Vectorize
mode requires the optional `vectorize` extra.

### Embed optimization

Embed mode preserves the source raster bytes by default. Opt in to resizing or
re-encoding only when a smaller raster payload is worth the quality trade-off:

```bash
svgconverter photo.jpg --max-width 1600 --jpeg-quality 82
svgconverter illustration.png --png-compress-level 9 --optimize-png
```

`--max-width` and `--max-height` only downscale and preserve aspect ratio.
`--jpeg-quality` applies only to JPEG inputs; `--png-compress-level` and
`--optimize-png` apply only to PNG inputs, so the same batch options are safe
for mixed formats. A resized JPEG without an explicit quality uses 95. The CLI
reports input, embedded-raster, and SVG sizes after each conversion or batch.
These controls apply to `embed` mode only.

## Python API

```python
from svgconverter import (
    ConversionProgress,
    EmbedOptions,
    SVGConverter,
    convert_file,
    convert_file_with_metrics,
    convert_paths,
)

convert_file("image.png", "image.svg")
convert_file("logo.png", "logo.svg", mode="vectorize")

converter = SVGConverter(overwrite=True)
result = converter.convert_directory("./images", "./svg-output", recursive=True)
metric = convert_file_with_metrics(
    "photo.jpg",
    "photo.svg",
    embed_options=EmbedOptions(max_width=1600, jpeg_quality=82),
)


def report(progress: ConversionProgress) -> None:
    print(progress.completed, progress.total, progress.input_path)


batch = convert_paths(
    ["logo.png", "photo.jpg"], "./svg-output", progress_callback=report
)
print(result.success_count, result.skipped_count, result.failure_count)
print(metric.input_bytes, metric.embedded_raster_bytes, metric.svg_bytes)
```

`convert_file()` returns the output `pathlib.Path`. Directory conversion returns
a `BatchResult` containing successful output paths and per-file failures, so a
bad image does not abort the entire batch. `convert_paths()` accepts a mix of
files and directories; existing batch outputs are recorded as skips unless
`overwrite=True` is selected. `EmbedOptions` is opt-in; without it, embed mode
uses the original raster bytes. `convert_file_with_metrics()` and
`BatchResult.metrics` report source, embedded-raster, and SVG byte sizes.
Use `progress_callback` for each processed item; return `True` from
`should_cancel` to stop cleanly before the next item. The result then has
`cancelled=True`.

## GUI

Install the package and run:

```bash
svgconverter-gui
```

The legacy development command `python main.py` starts the same GUI. Select one
or more files, or a folder, to convert with visible non-blocking progress and a
converted/skipped/failed summary. You can cancel between files; any per-file
errors are shown after the batch without closing the application. The GUI offers
Traditional Chinese, English, and Japanese and uses embed mode; vectorize mode
is available through the Python API and CLI.

For a supported release, Windows users can download the standalone
`SVGConverter-vX.Y.Z-windows-x86_64.exe` asset from the GitHub Release page; it
does not require a local Python installation.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for local checks and commit conventions.
This project is licensed under the [MIT License](LICENSE).
