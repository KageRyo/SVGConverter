# Contributing to SVGConverter

Thanks for helping improve SVGConverter. Please open an issue before a large
change so that the intended behavior is clear.

## Development setup

SVGConverter supports Python 3.10 or newer.

```bash
git clone https://github.com/KageRyo/SVGConverter.git
cd SVGConverter
python -m venv .venv
# Activate .venv using your shell's usual command.
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run the checks used by CI before opening a pull request:

```bash
ruff format --check .
ruff check .
pytest
python -m build
python -m twine check dist/*
```

## Scope and changes

The current `embed` mode stores a PNG or JPEG raster image in an SVG
`<image>` element. It is not vectorization. Please keep that distinction clear
in APIs, tests, CLI help, and documentation.

Use [Conventional Commits](https://www.conventionalcommits.org/) for commit
subjects, for example `fix: preserve JPEG MIME types` or
`feat(cli): add directory conversion`.
