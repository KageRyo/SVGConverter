"""Tkinter desktop interface built on the public batch conversion API."""

from __future__ import annotations

import tkinter as tk
from queue import Empty, Queue
from threading import Event, Thread
from tkinter import filedialog, messagebox, ttk
from typing import Literal

from .converter import (
    BatchResult,
    ConversionProgress,
    SVGConverterError,
    convert_paths,
)
from .i18n import (
    DEFAULT_LOCALE,
    load_translations,
    locale_for_display_name,
    translation_for,
)

_POLL_INTERVAL_MS = 75
_IMAGE_FILE_TYPES = [
    (
        "Supported images",
        "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff "
        "*.PNG *.JPG *.JPEG *.WEBP *.BMP *.TIF *.TIFF",
    ),
    ("All files", "*.*"),
]
_EventKind = Literal["progress", "done", "error"]
_GuiEvent = tuple[_EventKind, ConversionProgress | BatchResult | Exception]


def format_failure_details(result: BatchResult) -> str:
    """Return one readable line per failed file in a batch result."""

    return "\n".join(
        f"{failure.input_path.name}: {failure.error}" for failure in result.failed
    )


class SVGConverterApp:
    """The standalone GUI application."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("SVGConverter")
        self.translations = load_translations()
        self.locale = DEFAULT_LOCALE
        self._events: Queue[_GuiEvent] = Queue()
        self._cancel_event = Event()
        self._worker: Thread | None = None

        initial_name = translation_for(self.locale, self.translations)["name"]
        self.language_var = tk.StringVar(value=initial_name)
        self.status_var = tk.StringVar()

        controls = ttk.Frame(self.root, padding=20)
        controls.pack(fill=tk.BOTH, expand=True)
        self.files_button = ttk.Button(controls, command=self.select_files)
        self.files_button.pack(fill=tk.X)
        self.folder_button = ttk.Button(controls, command=self.select_folder)
        self.folder_button.pack(fill=tk.X, pady=(8, 0))
        self.cancel_button = ttk.Button(
            controls, command=self.cancel_conversion, state=tk.DISABLED
        )
        self.cancel_button.pack(fill=tk.X, pady=(8, 0))
        self.progress = ttk.Progressbar(controls, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(16, 0))
        self.status = ttk.Label(controls, textvariable=self.status_var, wraplength=360)
        self.status.pack(fill=tk.X, pady=(8, 0))
        self.language_menu = tk.OptionMenu(
            controls,
            self.language_var,
            *(text["name"] for text in self.translations.values()),
            command=self.change_language,
        )
        self.language_menu.pack(fill=tk.X, pady=(16, 0))
        self._refresh_text()

    @property
    def _text(self) -> dict[str, str]:
        return translation_for(self.locale, self.translations)

    def _refresh_text(self) -> None:
        text = self._text
        self.files_button.config(text=text["select_files"])
        self.folder_button.config(text=text["select_folder"])
        self.cancel_button.config(text=text["cancel"])
        if self._worker is None:
            self.status_var.set(text["ready"])

    def select_files(self) -> None:
        """Select one or more individual images for batch conversion."""

        files = filedialog.askopenfilenames(
            parent=self.root,
            title=self._text["select_files"],
            filetypes=_IMAGE_FILE_TYPES,
        )
        if files:
            self._start_conversion(files)

    def select_folder(self) -> None:
        """Select a folder whose immediate supported images will be converted."""

        folder = filedialog.askdirectory(
            parent=self.root, title=self._text["select_folder"]
        )
        if folder:
            self._start_conversion((folder,))

    def _start_conversion(self, input_paths: tuple[str, ...] | list[str]) -> None:
        self._cancel_event.clear()
        self._set_running(True)
        self.progress.configure(value=0, maximum=1)
        self.status_var.set(self._text["starting"])
        self._worker = Thread(
            target=self._run_conversion,
            args=(input_paths,),
            daemon=True,
        )
        self._worker.start()
        self.root.after(_POLL_INTERVAL_MS, self._poll_events)

    def _run_conversion(self, input_paths: tuple[str, ...] | list[str]) -> None:
        try:
            result = convert_paths(
                input_paths,
                progress_callback=self._report_progress,
                should_cancel=self._cancel_event.is_set,
            )
        except SVGConverterError as error:
            self._events.put(("error", error))
        except Exception as error:  # Keep unexpected worker failures visible in the UI.
            self._events.put(("error", error))
        else:
            self._events.put(("done", result))

    def _report_progress(self, progress: ConversionProgress) -> None:
        self._events.put(("progress", progress))

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "progress":
                    self._show_progress(payload)
                elif kind == "done":
                    self._show_result(payload)
                else:
                    self._show_error(payload)
        except Empty:
            pass

        if self._worker is not None:
            self.root.after(_POLL_INTERVAL_MS, self._poll_events)

    def _show_progress(
        self, progress: ConversionProgress | BatchResult | Exception
    ) -> None:
        if not isinstance(progress, ConversionProgress):
            return
        self.progress.configure(
            maximum=max(progress.total, 1), value=progress.completed
        )
        self.status_var.set(
            self._text["progress"].format(
                completed=progress.completed,
                total=progress.total,
                current=progress.input_path.name,
                converted=progress.converted,
                skipped=progress.skipped,
                failed=progress.failed,
            )
        )

    def _show_result(
        self, result: ConversionProgress | BatchResult | Exception
    ) -> None:
        if not isinstance(result, BatchResult):
            return
        self._set_running(False)
        message_key = "cancelled" if result.cancelled else "done"
        message = self._text[message_key].format(
            converted=result.success_count,
            skipped=result.skipped_count,
            failed=result.failure_count,
        )
        self.status_var.set(message)
        if result.failed:
            details = format_failure_details(result)
            messagebox.showwarning(
                self._text["errors_title"],
                f"{message}\n\n{details}",
                parent=self.root,
            )
        else:
            messagebox.showinfo("SVGConverter", message, parent=self.root)

    def _show_error(self, error: ConversionProgress | BatchResult | Exception) -> None:
        self._set_running(False)
        self.status_var.set(self._text["error"])
        messagebox.showerror("SVGConverter", str(error), parent=self.root)

    def _set_running(self, running: bool) -> None:
        state = tk.DISABLED if running else tk.NORMAL
        self.files_button.config(state=state)
        self.folder_button.config(state=state)
        self.cancel_button.config(state=tk.NORMAL if running else tk.DISABLED)
        if not running:
            self._worker = None

    def cancel_conversion(self) -> None:
        """Request a clean stop after the image currently being processed."""

        self._cancel_event.set()
        self.cancel_button.config(state=tk.DISABLED)
        self.status_var.set(self._text["cancelling"])

    def change_language(self, display_name: str) -> None:
        self.locale = locale_for_display_name(display_name, self.translations)
        self._refresh_text()

    def run(self) -> None:
        """Start the Tkinter event loop."""

        self.root.mainloop()


def run_gui() -> None:
    """Launch the SVGConverter desktop interface."""

    SVGConverterApp().run()
