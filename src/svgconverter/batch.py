"""Batch candidate planning, collision handling, and progress execution."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from .embed import SUPPORTED_EXTENSIONS
from .errors import (
    InputPathError,
    OutputCollisionError,
    SVGConverterError,
)
from .models import (
    BatchResult,
    CancelCallback,
    ConversionFailure,
    ConversionMetrics,
    ConversionMode,
    ConversionProgress,
    ConversionSkip,
    EmbedOptions,
    ProgressCallback,
    VectorizeOptions,
)
from .paths import ensure_within_root, resolve_allowed_root

Candidate = tuple[Path, Path]
FileConverter = Callable[..., ConversionMetrics]


def validate_output_directory(destination_directory: Path) -> None:
    """Validate an optional output directory without creating it yet."""

    if destination_directory.exists() and not destination_directory.is_dir():
        raise InputPathError(
            f"Output directory path is not a directory: {destination_directory}"
        )


def directory_candidates(
    source_directory: Path,
    destination_directory: Path,
    *,
    recursive: bool,
) -> list[Candidate]:
    """Plan supported source files and their relative output paths."""

    entries = source_directory.rglob("*") if recursive else source_directory.iterdir()
    sources = sorted(
        (
            path
            for path in entries
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ),
        key=lambda path: str(path.relative_to(source_directory)).casefold(),
    )
    return [
        (
            source,
            destination_directory
            / source.relative_to(source_directory).with_suffix(".svg"),
        )
        for source in sources
    ]


def _directory_output(
    source: Path,
    destination_directory: Path | None,
    *,
    prefix_directories: bool,
) -> Path:
    if destination_directory is None:
        return source
    if prefix_directories:
        return destination_directory / source.name
    return destination_directory


def _file_candidate(source: Path, destination_directory: Path | None) -> Candidate:
    destination = (
        source.with_suffix(".svg")
        if destination_directory is None
        else destination_directory / source.with_suffix(".svg").name
    )
    return source, destination


def _missing_file_failure(source: Path) -> ConversionFailure:
    return ConversionFailure(
        input_path=source,
        error=InputPathError(f"Input file does not exist: {source}"),
    )


def path_candidates(
    input_paths: Iterable[str | Path],
    output_dir: str | Path | None,
    *,
    recursive: bool,
    allowed_root: str | Path | None = None,
) -> tuple[list[Candidate], list[ConversionFailure]]:
    """Plan file and directory inputs while preserving missing-file failures."""

    path_root = resolve_allowed_root(allowed_root)
    source_paths = tuple(
        ensure_within_root(input_path, path_root, label="Input path")
        for input_path in input_paths
    )
    if not source_paths:
        raise InputPathError("At least one input file or directory is required.")

    destination_directory = (
        ensure_within_root(output_dir, path_root, label="Output directory")
        if output_dir is not None
        else None
    )
    if destination_directory is not None:
        validate_output_directory(destination_directory)

    directory_inputs = tuple(path for path in source_paths if path.is_dir())
    prefix_directories = len(directory_inputs) > 1
    candidates: list[Candidate] = []
    initial_failures: list[ConversionFailure] = []
    for source in source_paths:
        if source.is_dir():
            directory_output = _directory_output(
                source,
                destination_directory,
                prefix_directories=prefix_directories,
            )
            candidates.extend(
                directory_candidates(source, directory_output, recursive=recursive)
            )
            continue

        candidate = _file_candidate(source, destination_directory)
        if not source.exists():
            initial_failures.append(_missing_file_failure(source))
            continue
        candidates.append(candidate)

    return candidates, initial_failures


def _unique_candidates(candidates: Iterable[Candidate]) -> list[Candidate]:
    unique_candidates: list[Candidate] = []
    seen_candidates: set[Candidate] = set()
    for candidate in candidates:
        if candidate in seen_candidates:
            continue
        unique_candidates.append(candidate)
        seen_candidates.add(candidate)
    return unique_candidates


def _colliding_destinations(
    candidates: Iterable[Candidate],
) -> tuple[dict[Path, list[Path]], set[Path]]:
    sources_by_destination: dict[Path, list[Path]] = {}
    for source, destination in candidates:
        sources_by_destination.setdefault(destination, []).append(source)
    colliding_destinations = {
        destination
        for destination, sources in sources_by_destination.items()
        if len(sources) > 1
    }
    return sources_by_destination, colliding_destinations


def _collision_failure(
    source: Path,
    destination: Path,
    sources_by_destination: dict[Path, list[Path]],
) -> ConversionFailure:
    colliding_sources = ", ".join(
        str(candidate) for candidate in sources_by_destination[destination]
    )
    return ConversionFailure(
        input_path=source,
        error=OutputCollisionError(
            "Batch inputs would create the same output "
            f"{destination}: {colliding_sources}"
        ),
    )


def _process_candidate(
    source: Path,
    destination: Path,
    *,
    colliding_destinations: set[Path],
    sources_by_destination: dict[Path, list[Path]],
    convert_file: FileConverter,
    overwrite: bool,
    mode: ConversionMode,
    vectorize_options: VectorizeOptions | None,
    embed_options: EmbedOptions | None,
    allowed_root: str | Path | None,
) -> tuple[ConversionMetrics | None, ConversionSkip | None, ConversionFailure | None]:
    if destination in colliding_destinations:
        return (
            None,
            None,
            _collision_failure(source, destination, sources_by_destination),
        )
    if destination.exists() and destination.is_dir():
        return (
            None,
            None,
            ConversionFailure(
                input_path=source,
                error=InputPathError(f"Output path is a directory: {destination}"),
            ),
        )
    if destination.exists() and not overwrite:
        return (
            None,
            ConversionSkip(
                input_path=source,
                output_path=destination,
                reason="output already exists",
            ),
            None,
        )
    try:
        metric = convert_file(
            source,
            destination,
            overwrite=overwrite,
            mode=mode,
            vectorize_options=vectorize_options,
            embed_options=embed_options,
            allowed_root=allowed_root,
        )
    except SVGConverterError as error:
        return None, None, ConversionFailure(input_path=source, error=error)
    return metric, None, None


def _report_progress(
    progress_callback: ProgressCallback | None,
    *,
    source: Path,
    completed: int,
    total: int,
    converted: list[Path],
    skipped: list[ConversionSkip],
    failed: list[ConversionFailure],
) -> None:
    if progress_callback is None:
        return
    progress_callback(
        ConversionProgress(
            input_path=source,
            completed=completed,
            total=total,
            converted=len(converted),
            skipped=len(skipped),
            failed=len(failed),
        )
    )


def convert_candidates(
    candidates: Iterable[Candidate],
    *,
    convert_file: FileConverter,
    overwrite: bool,
    mode: ConversionMode,
    vectorize_options: VectorizeOptions | None,
    embed_options: EmbedOptions | None,
    allowed_root: str | Path | None = None,
    progress_callback: ProgressCallback | None = None,
    should_cancel: CancelCallback | None = None,
    initial_failures: Iterable[ConversionFailure] = (),
) -> BatchResult:
    """Convert planned source/output pairs with predictable batch semantics."""

    unique_candidates = _unique_candidates(candidates)
    sources_by_destination, colliding_destinations = _colliding_destinations(
        unique_candidates
    )

    converted: list[Path] = []
    skipped: list[ConversionSkip] = []
    metrics: list[ConversionMetrics] = []
    failed = list(initial_failures)
    completed = 0
    cancelled = False
    for source, destination in unique_candidates:
        if should_cancel is not None and should_cancel():
            cancelled = True
            break
        metric, skip, failure = _process_candidate(
            source,
            destination,
            colliding_destinations=colliding_destinations,
            sources_by_destination=sources_by_destination,
            convert_file=convert_file,
            overwrite=overwrite,
            mode=mode,
            vectorize_options=vectorize_options,
            embed_options=embed_options,
            allowed_root=allowed_root,
        )
        if metric is not None:
            converted.append(metric.output_path)
            metrics.append(metric)
        if skip is not None:
            skipped.append(skip)
        if failure is not None:
            failed.append(failure)

        completed += 1
        _report_progress(
            progress_callback,
            source=source,
            completed=completed,
            total=len(unique_candidates),
            converted=converted,
            skipped=skipped,
            failed=failed,
        )

    return BatchResult(
        converted=tuple(converted),
        failed=tuple(failed),
        skipped=tuple(skipped),
        metrics=tuple(metrics),
        cancelled=cancelled,
    )
