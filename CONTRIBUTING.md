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

SVGConverter has two distinct conversion modes. `embed` stores a PNG or JPEG
raster image in an SVG `<image>` element; `vectorize` creates SVG paths. Keep
their different output, quality, and dependency requirements clear in APIs,
tests, CLI help, and documentation.

## GitHub Flow

`main` must remain releasable. Use this workflow for every change:

1. Start a descriptive branch from current `main`, such as `feat/vectorize` or
   `fix/jpeg-mime`.
2. Make focused Conventional Commits and run the local checks above.
3. Open a pull request targeting `main`; explain user-visible behavior and link
   relevant issues.
4. Wait for required CI checks and review feedback to be resolved.
5. Squash merge the PR. Do not directly push feature changes to `main`.

See [RELEASING.md](RELEASING.md) for the maintainer-only tag and PyPI process.

Use [Conventional Commits](https://www.conventionalcommits.org/) for commit
subjects, for example `fix: preserve JPEG MIME types` or
`feat(cli): add directory conversion`.
