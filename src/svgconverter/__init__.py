"""Public library interface for SVGConverter.

SVGConverter's current ``embed`` mode wraps raster image bytes in an SVG
``<image>`` element. It does not trace images into vector paths.
"""

from .converter import (
    BatchResult,
    ConversionError,
    ConversionFailure,
    InputPathError,
    OutputExistsError,
    SVGConverter,
    SVGConverterError,
    UnsupportedImageError,
    convert_directory,
    convert_file,
)

__all__ = [
    "BatchResult",
    "ConversionError",
    "ConversionFailure",
    "InputPathError",
    "OutputExistsError",
    "SVGConverter",
    "SVGConverterError",
    "UnsupportedImageError",
    "convert_directory",
    "convert_file",
]

__version__ = "1.2.0"
