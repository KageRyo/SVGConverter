"""Conservative whitespace compaction of validated, generated SVG documents."""

import re
from pathlib import Path
from xml.dom import Node, minidom
from xml.parsers.expat import ExpatError

from .errors import ConversionError

_SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
_PATH_COMMAND_SPACE = re.compile(r"\s*([AaCcHhLlMmQqSsTtVvZz])\s*")
# Only these element-only containers have ignorable indentation. In particular,
# never descend into text, style, scripts, or foreign content.
_CONTAINERS = {
    "svg",
    "g",
    "defs",
    "linearGradient",
    "radialGradient",
    "clipPath",
    "mask",
}


def _compact(element: minidom.Element, preserve_space: bool = False) -> None:
    space = element.getAttributeNS(_XML_NAMESPACE, "space")
    if space:
        preserve_space = space == "preserve"
    if element.namespaceURI == _SVG_NAMESPACE and element.localName == "path":
        # Command letters delimit path tokens without whitespace. Keep every
        # number unchanged, including exponent notation and arc flags.
        if element.hasAttribute("d"):
            path_data = element.getAttribute("d")
            element.setAttribute("d", _PATH_COMMAND_SPACE.sub(r"\1", path_data.strip()))
    if element.namespaceURI != _SVG_NAMESPACE or element.localName not in _CONTAINERS:
        return
    for child in list(element.childNodes):
        if child.nodeType == Node.TEXT_NODE:
            if not preserve_space and not child.nodeValue.strip():
                element.removeChild(child)
                child.unlink()
        elif isinstance(child, minidom.Element):
            _compact(child, preserve_space)


def optimize_svg_file(path: Path) -> None:
    """Compact a staged SVG after conversion validation, retaining smaller bytes.

    Coordinates, comments, significant text, and namespace bindings
    retain their XML meaning. No external optimizer or geometry rewrite is used.
    This internal function only receives a document validated by the converter,
    which rejects custom entities before any DOM parsing.
    """

    try:
        original = path.read_bytes()
        with minidom.parseString(original) as document:
            root = document.documentElement
            if root is None:
                raise ConversionError("Cannot optimize an SVG without a root element.")
            _compact(root)
            compact = document.toxml(encoding="utf-8")
        if len(compact) < len(original):
            path.write_bytes(compact)
    except (OSError, ExpatError, ValueError) as error:
        raise ConversionError(f"Cannot optimize SVG {path}: {error}") from error
