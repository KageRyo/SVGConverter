"""Public library interface for SVGConverter.

SVGConverter's current ``embed`` mode wraps raster image bytes in an SVG
``<image>`` element. It does not trace images into vector paths.
"""

from .converter import (
    BatchResult,
    ConversionError,
    ConversionFailure,
    ConversionMode,
    InputPathError,
    OutputExistsError,
    SVGConverter,
    SVGConverterError,
    UnsupportedImageError,
    VectorizationDependencyError,
    VectorizeOptions,
    convert_directory,
    convert_file,
)

__all__ = [
    "BatchResult",
    "ConversionMode",
    "ConversionError",
    "ConversionFailure",
    "InputPathError",
    "OutputExistsError",
    "SVGConverter",
    "SVGConverterError",
    "UnsupportedImageError",
    "VectorizationDependencyError",
    "VectorizeOptions",
    "convert_directory",
    "convert_file",
]

__version__ = "1.3.0"
