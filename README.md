# SVGConverter

[正體中文](README_TW.md)

SVGConverter wraps a PNG or JPEG image in an SVG container. It provides a
small Python API, command-line interface, and desktop GUI.

> **Important:** current `embed` mode Base64-encodes the original raster image
> into an SVG `<image>` element. It does **not** trace pixels into vector paths,
> and it does not inherently reduce file size. A future `vectorize` mode is
> tracked separately.

## Installation

SVGConverter requires Python 3.10 or newer. After v1.2.0 has been published to
PyPI:

```bash
python -m pip install --upgrade svgconverter
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
```

Convert all supported images immediately inside a directory:

```bash
svgconverter ./images --output-dir ./svg-output
```

Outputs are never overwritten unless `--overwrite` is supplied. Run
`svgconverter --help` for all options. Supported inputs are PNG, JPG, and JPEG
(including upper-case extensions); recursive conversion and image optimization
are not part of the current release.

## Python API

```python
from svgconverter import SVGConverter, convert_file

convert_file("image.png", "image.svg")

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
Japanese. It uses the same public conversion API as the CLI.

## Release process

The tag workflow uses [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
instead of a long-lived API token. Before the first release, configure a
pending or normal PyPI Trusted Publisher for:

- owner: `KageRyo`
- repository: `SVGConverter`
- workflow: `release.yml`
- environment: `pypi`

After the pull request is merged, create an annotated `v1.2.0` tag whose
version matches `pyproject.toml`. The workflow builds, checks, publishes to
PyPI, and then creates a GitHub Release with the distributions attached.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for local checks and commit conventions.
This project is licensed under the [MIT License](LICENSE).
