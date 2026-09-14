"""Filesystem path boundary helpers for trusted and untrusted integrations."""

from __future__ import annotations

from pathlib import Path

from .errors import InputPathError


def resolve_allowed_root(allowed_root: str | Path | None) -> Path | None:
    """Resolve and validate an optional root used to constrain filesystem paths."""

    if allowed_root is None:
        return None

    root = Path(allowed_root)
    try:
        resolved_root = root.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise InputPathError(f"Cannot resolve allowed root: {root}") from error
    if resolved_root.exists() and not resolved_root.is_dir():
        raise InputPathError(f"Allowed root is not a directory: {root}")
    return resolved_root


def ensure_within_root(
    path: str | Path,
    allowed_root: Path | None,
    *,
    label: str,
) -> Path:
    """Return a path resolved inside ``allowed_root`` when a root is configured.

    With no root configured, paths retain their existing behavior so the local
    CLI and library API can continue to work with arbitrary user-selected
    locations. Integrations that accept paths from an untrusted caller should
    provide an explicit root.
    """

    candidate = Path(path)
    if allowed_root is None:
        return candidate

    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(allowed_root)
    except (OSError, RuntimeError, ValueError) as error:
        raise InputPathError(
            f"{label} must be within allowed root {allowed_root}: {candidate}"
        ) from error
    return resolved
