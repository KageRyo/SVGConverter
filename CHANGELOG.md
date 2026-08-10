# Changelog

All notable changes to SVGConverter are documented in this file.

This project follows [Semantic Versioning](https://semver.org/) and uses
[Conventional Commits](https://www.conventionalcommits.org/).

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
