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


def path_candidates(
    input_paths: Iterable[str | Path],
    output_dir: str | Path | None,
    *,
    recursive: bool,
) -> tuple[list[Candidate], list[ConversionFailure]]:
    """Plan file and directory inputs while preserving missing-file failures."""

    source_paths = tuple(Path(input_path) for input_path in input_paths)
    if not source_paths:
        raise InputPathError("At least one input file or directory is required.")

    destination_directory = Path(output_dir) if output_dir is not None else None
    if destination_directory is not None:
        validate_output_directory(destination_directory)

    directory_inputs = tuple(path for path in source_paths if path.is_dir())
    prefix_directories = len(directory_inputs) > 1
    candidates: list[Candidate] = []
    initial_failures: list[ConversionFailure] = []
    for source in source_paths:
        if source.is_dir():
            directory_output = (
                source if destination_directory is None else destination_directory
            )
            if destination_directory is not None and prefix_directories:
                directory_output = destination_directory / source.name
            candidates.extend(
                directory_candidates(source, directory_output, recursive=recursive)
            )
            continue

        destination = (
            source.with_suffix(".svg")
            if destination_directory is None
            else destination_directory / source.with_suffix(".svg").name
        )
        if not source.exists():
            initial_failures.append(
                ConversionFailure(
                    input_path=source,
                    error=InputPathError(f"Input file does not exist: {source}"),
                )
            )
            continue
        candidates.append((source, destination))

    return candidates, initial_failures


def convert_candidates(
    candidates: Iterable[Candidate],
    *,
    convert_file: FileConverter,
    overwrite: bool,
    mode: ConversionMode,
    vectorize_options: VectorizeOptions | None,
    embed_options: EmbedOptions | None,
    progress_callback: ProgressCallback | None = None,
    should_cancel: CancelCallback | None = None,
    initial_failures: Iterable[ConversionFailure] = (),
) -> BatchResult:
    """Convert planned source/output pairs with predictable batch semantics."""

    unique_candidates: list[Candidate] = []
    seen_candidates: set[Candidate] = set()
    for candidate in candidates:
        if candidate not in seen_candidates:
            unique_candidates.append(candidate)
            seen_candidates.add(candidate)

    sources_by_destination: dict[Path, list[Path]] = {}
    for source, destination in unique_candidates:
        sources_by_destination.setdefault(destination, []).append(source)
    colliding_destinations = {
        destination
        for destination, sources in sources_by_destination.items()
        if len(sources) > 1
    }

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
        if destination in colliding_destinations:
            colliding_sources = ", ".join(
                str(candidate) for candidate in sources_by_destination[destination]
            )
            failed.append(
                ConversionFailure(
                    input_path=source,
                    error=OutputCollisionError(
                        "Batch inputs would create the same output "
                        f"{destination}: {colliding_sources}"
                    ),
                )
            )
        elif destination.exists() and destination.is_dir():
            failed.append(
                ConversionFailure(
                    input_path=source,
                    error=InputPathError(f"Output path is a directory: {destination}"),
                )
            )
        elif destination.exists() and not overwrite:
            skipped.append(
                ConversionSkip(
                    input_path=source,
                    output_path=destination,
                    reason="output already exists",
                )
            )
        else:
            try:
                metric = convert_file(
                    source,
                    destination,
                    overwrite=overwrite,
                    mode=mode,
                    vectorize_options=vectorize_options,
                    embed_options=embed_options,
                )
                converted.append(metric.output_path)
                metrics.append(metric)
            except SVGConverterError as error:
                failed.append(ConversionFailure(input_path=source, error=error))

        completed += 1
        if progress_callback is not None:
            progress_callback(
                ConversionProgress(
                    input_path=source,
                    completed=completed,
                    total=len(unique_candidates),
                    converted=len(converted),
                    skipped=len(skipped),
                    failed=len(failed),
                )
            )

    return BatchResult(
        converted=tuple(converted),
        failed=tuple(failed),
        skipped=tuple(skipped),
        metrics=tuple(metrics),
        cancelled=cancelled,
    )
