"""Exception hierarchy for SVGConverter."""

from __future__ import annotations


class SVGConverterError(Exception):
    """Base exception for expected SVGConverter failures."""


class InputPathError(SVGConverterError):
    """Raised when an input path is missing or is the wrong kind of path."""


class UnsupportedImageError(SVGConverterError):
    """Raised when an input is not a supported raster image."""


class OutputExistsError(SVGConverterError):
    """Raised when conversion would overwrite an existing SVG."""


class OutputCollisionError(SVGConverterError):
    """Raised when batch inputs would create the same output SVG path."""


class ConversionError(SVGConverterError):
    """Raised when an image cannot be read or an SVG cannot be written."""


class VectorizationDependencyError(SVGConverterError):
    """Raised when vectorize mode is used without its optional backend."""
