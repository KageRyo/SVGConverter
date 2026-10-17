"""Run the complete native preview pipeline outside Tk's Python interpreter."""

from __future__ import annotations

import multiprocessing
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from .errors import VectorizationDependencyError
from .models import ConversionMode, EmbedOptions, VectorizeOptions
from .preview import (
    PreviewDependencyError,
    PreviewError,
    PreviewResult,
    _check_cancelled,
    _create_preview_in_directory,
)


@dataclass(frozen=True)
class _PreviewRequest:
    input_path: Path
    mode: ConversionMode
    embed_options: EmbedOptions | None
    vectorize_options: VectorizeOptions | None
    thumbnail_size: tuple[int, int]


@dataclass(frozen=True)
class _PreviewFailure:
    kind: Literal["renderer", "vectorize", "error"]
    message: str


def _preview_worker(
    sender: Connection, request: _PreviewRequest, directory: Path
) -> None:
    """Return detached thumbnails or a small, serializable error description."""

    try:
        result = _create_preview_in_directory(
            request.input_path,
            directory,
            mode=request.mode,
            embed_options=request.embed_options,
            vectorize_options=request.vectorize_options,
            thumbnail_size=request.thumbnail_size,
        )
    except PreviewDependencyError as error:
        sender.send(_PreviewFailure("renderer", str(error)))
    except Exception as error:
        kind = (
            "vectorize"
            if isinstance(error.__cause__, VectorizationDependencyError)
            else "error"
        )
        sender.send(_PreviewFailure(kind, str(error)))
    else:
        sender.send(result)
    finally:
        sender.close()


def _decode_result(message: object) -> PreviewResult:
    if isinstance(message, PreviewResult):
        return message
    if isinstance(message, _PreviewFailure):
        if message.kind == "renderer":
            raise PreviewDependencyError(message.message)
        if message.kind == "vectorize":
            raise PreviewError(message.message) from VectorizationDependencyError(
                message.message
            )
        raise PreviewError(message.message)
    raise PreviewError("Preview worker returned an invalid result.")


def _receive_result(
    receiver: Connection,
    process: BaseProcess,
    should_cancel: Callable[[], bool] | None,
) -> PreviewResult:
    while True:
        _check_cancelled(should_cancel)
        if receiver.poll(0.05):
            try:
                message = receiver.recv()
            except (EOFError, OSError) as error:
                process.join(timeout=1)
                raise PreviewError(
                    "Preview worker exited without a result "
                    f"(exit code {process.exitcode})."
                ) from error
            _check_cancelled(should_cancel)
            return _decode_result(message)
        if not process.is_alive() and not receiver.poll():
            raise PreviewError(
                "Preview worker exited without a result "
                f"(exit code {process.exitcode})."
            )


def _stop_process(process: BaseProcess) -> None:
    """Reap the child before its parent's temporary-directory context exits."""

    if process.pid is not None:
        process.join(timeout=0.1)
        if process.is_alive():
            process.terminate()
        process.join(timeout=1)
        if process.is_alive():
            process.kill()
            process.join()
    process.close()


def create_preview(
    input_path: str | Path,
    *,
    mode: ConversionMode = "embed",
    embed_options: EmbedOptions | None = None,
    vectorize_options: VectorizeOptions | None = None,
    should_cancel: Callable[[], bool] | None = None,
    thumbnail_size: tuple[int, int] = (360, 360),
) -> PreviewResult:
    """Spawn a preview process and cancel it without waiting for native work.

    The supervising caller owns the private directory. On success, cancellation,
    startup failure, or child failure, it reaps the child before removing files.
    No Tk object, cancellation callback, or final output path enters the child.
    """

    _check_cancelled(should_cancel)
    request = _PreviewRequest(
        Path(input_path), mode, embed_options, vectorize_options, thumbnail_size
    )
    context = multiprocessing.get_context("spawn")
    with TemporaryDirectory(prefix="svgconverter-preview-") as directory:
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(
            target=_preview_worker, args=(sender, request, Path(directory)), daemon=True
        )
        try:
            try:
                process.start()
            except (OSError, RuntimeError) as error:
                raise PreviewError(f"Cannot start preview worker: {error}") from error
            sender.close()
            return _receive_result(receiver, process, should_cancel)
        finally:
            sender.close()
            receiver.close()
            _stop_process(process)
