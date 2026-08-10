# Changelog

All notable changes to SVGConverter are documented in this file.

This project follows [Semantic Versioning](https://semver.org/) and uses
[Conventional Commits](https://www.conventionalcommits.org/).

## Unreleased (planned v1.2.0)

### Added

- Installable `src/svgconverter` package, public Python API, and CLI.
- Separate `svgconverter-gui` command and package-safe localization resources.
- Automated tests, Ruff checks, package build checks, and CI.
- A tag-driven PyPI Trusted Publishing workflow.

### Changed

- Clarified that the current conversion mode embeds raster bytes in SVG; it
  does not produce vector paths.
- PNG and JPEG data URIs now use their actual MIME types.
