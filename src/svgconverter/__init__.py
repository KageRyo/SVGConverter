"""Public library interface for SVGConverter.

SVGConverter's current ``embed`` mode wraps raster image bytes in an SVG
``<image>`` element. It does not trace images into vector paths.
"""

from .converter import (
    BatchResult,
    ConversionError,
    ConversionFailure,
    ConversionMode,
    ConversionSkip,
    InputPathError,
    OutputCollisionError,
    OutputExistsError,
    SVGConverter,
    SVGConverterError,
    UnsupportedImageError,
    VectorizationDependencyError,
    VectorizeOptions,
    convert_directory,
    convert_file,
    convert_paths,
)

__all__ = [
    "BatchResult",
    "ConversionMode",
    "ConversionError",
    "ConversionFailure",
    "ConversionSkip",
    "InputPathError",
    "OutputExistsError",
    "OutputCollisionError",
    "SVGConverter",
    "SVGConverterError",
    "UnsupportedImageError",
    "VectorizationDependencyError",
    "VectorizeOptions",
    "convert_directory",
    "convert_file",
    "convert_paths",
]

__version__ = "1.3.0"
