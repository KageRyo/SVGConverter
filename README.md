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

Outputs are never overwritten unless `--overwrite` is supplied. Run
`svgconverter --help` for all options. Supported inputs are PNG, JPG, JPEG,
WebP, BMP, TIF, and TIFF (including upper-case extensions); recursive
conversion and image optimization are not part of the current release.
Vectorize mode requires the optional `vectorize` extra.

## Python API

```python
from svgconverter import SVGConverter, convert_file

convert_file("image.png", "image.svg")
convert_file("logo.png", "logo.svg", mode="vectorize")

converter = SVGConverter(overwrite=True)
result = converter.convert_directory("./images", "./svg-output")
print(result.success_count, result.failure_count)
```

`convert_file()` returns the output `pathlib.Path`. Directory conversion returns
a `BatchResult` containing successful output paths and per-file failures, so a
bad image does not abort the entire batch.

## GUI

Install the package and run:

```bash
svgconverter-gui
```

The legacy development command `python main.py` starts the same GUI. The GUI
currently selects a directory and offers Traditional Chinese, English, and
Japanese. It uses embed mode; vectorize mode is available through the Python
API and CLI.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for local checks and commit conventions.
This project is licensed under the [MIT License](LICENSE).
