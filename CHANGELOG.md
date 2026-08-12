# Changelog

All notable changes to SVGConverter are documented in this file.

This project follows [Semantic Versioning](https://semver.org/) and uses
[Conventional Commits](https://www.conventionalcommits.org/).

## Unreleased

### Added

- GUI file selection, non-blocking batch progress, cancellation, and per-file
  failure details.
- Windows CI builds a standalone GUI executable and attaches it to tagged
  GitHub Releases.

### Changed

- Batch API callers can receive per-file progress updates and request a clean
  cancellation between files.

## 1.4.0 - 2026-08-12

### Added

- WebP, BMP, and TIFF input support in embed and vectorize modes, including
  correct self-contained data URI MIME types.
- Opt-in recursive directory conversion that preserves nested output paths.
- Multi-input batch conversion through the Python API and CLI.
- Opt-in embed raster preprocessing for downscaling, JPEG quality, and PNG
  compression/optimization.

### Changed

- Batch conversion now reports converted, skipped, and failed items; existing
  SVG outputs are skipped unless overwrite is explicitly requested.
- Conversion metrics report source, embedded-raster, and SVG byte sizes.

## 1.3.0 - 2026-08-10

### Added

- Optional VTracer-backed `vectorize` mode for actual SVG path generation.
- Vectorize CLI controls for colour handling, curve fitting, and output detail.
- GitHub Flow guidance and a separate maintainer release guide.

### Changed

- User README files now focus on usage and conversion behavior rather than
  maintainer release operations.

## 1.2.0 - 2026-08-10

### Added

- Installable `src/svgconverter` package, public Python API, and CLI.
- Separate `svgconverter-gui` command and package-safe localization resources.
- Automated tests, Ruff checks, package build checks, and CI.
- A tag-driven PyPI Trusted Publishing workflow.

### Changed

- Clarified that the current conversion mode embeds raster bytes in SVG; it
  does not produce vector paths.
- PNG and JPEG data URIs now use their actual MIME types.
