"""Public library interface for SVGConverter.

SVGConverter's current ``embed`` mode wraps raster image bytes in an SVG
``<image>`` element. It does not trace images into vector paths.
"""

from .converter import (
    BatchResult,
    ConversionError,
    ConversionFailure,
    ConversionMetrics,
    ConversionMode,
    ConversionSkip,
    EmbedOptions,
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
    convert_file_with_metrics,
    convert_paths,
)

__all__ = [
    "BatchResult",
    "ConversionMode",
    "ConversionError",
    "ConversionFailure",
    "ConversionMetrics",
    "ConversionSkip",
    "EmbedOptions",
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
    "convert_file_with_metrics",
    "convert_paths",
]

__version__ = "1.4.0"
