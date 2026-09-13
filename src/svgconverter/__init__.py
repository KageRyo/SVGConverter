"""Public library interface for SVGConverter.

SVGConverter's current ``embed`` mode wraps raster image bytes in an SVG
``<image>`` element. It does not trace images into vector paths.
"""

from .converter import (
    SVGConverter,
    convert_directory,
    convert_file,
    convert_file_with_metrics,
    convert_paths,
)
from .errors import (
    ConversionError,
    InputPathError,
    OutputCollisionError,
    OutputExistsError,
    SVGConverterError,
    UnsupportedImageError,
    VectorizationDependencyError,
)
from .models import (
    BatchResult,
    ConversionFailure,
    ConversionMetrics,
    ConversionMode,
    ConversionProgress,
    ConversionSkip,
    EmbedOptions,
    VectorizeOptions,
)

__all__ = [
    "BatchResult",
    "ConversionMode",
    "ConversionError",
    "ConversionFailure",
    "ConversionMetrics",
    "ConversionProgress",
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

__version__ = "1.5.0"
