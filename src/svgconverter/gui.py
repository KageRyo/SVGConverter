"""Tkinter desktop interface built on the public batch conversion API."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Thread
from tkinter import filedialog, messagebox, ttk
from typing import Literal, cast

from .converter import (
    BatchResult,
    ConversionMode,
    ConversionProgress,
    EmbedOptions,
    SVGConverterError,
    VectorizeColorMode,
    VectorizeCurveMode,
    VectorizeHierarchy,
    VectorizeOptions,
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
_VECTORIZE_COLOR_MODES = ("color", "binary")
_VECTORIZE_HIERARCHIES = ("stacked", "cutout")
_VECTORIZE_CURVE_MODES = ("pixel", "polygon", "spline")


@dataclass(frozen=True)
class GuiConversionOptions:
    """A validated snapshot of settings captured before a GUI batch starts."""

    mode: ConversionMode
    output_dir: str | None
    overwrite: bool
    recursive: bool
    embed_options: EmbedOptions | None
    vectorize_options: VectorizeOptions | None


def _optional_int(value: str | int | None, label: str) -> int | None:
    """Parse an optional integer entry, treating an empty value as unset."""

    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a whole number.") from error


def build_embed_options(
    *,
    max_width: str | int | None = None,
    max_height: str | int | None = None,
    jpeg_quality: str | int | None = None,
    png_compress_level: str | int | None = None,
    optimize_png: bool = False,
) -> EmbedOptions | None:
    """Build embed options from the GUI's text fields.

    Returning ``None`` when every field is at its default preserves the core
    API's byte-for-byte embed behavior.
    """

    options = EmbedOptions(
        max_width=_optional_int(max_width, "Maximum width"),
        max_height=_optional_int(max_height, "Maximum height"),
        jpeg_quality=_optional_int(jpeg_quality, "JPEG quality"),
        png_compress_level=_optional_int(png_compress_level, "PNG compression level"),
        optimize_png=optimize_png,
    )
    return options if options.is_enabled else None


def _choice(value: str, choices: tuple[str, ...], label: str) -> str:
    if value not in choices:
        choices_text = ", ".join(choices)
        raise ValueError(f"{label} must be one of: {choices_text}.")
    return value


def build_vectorize_options(
    *,
    color_mode: str = "color",
    hierarchical: str = "stacked",
    curve_mode: str = "spline",
    filter_speckle: str | int | None = None,
    color_precision: str | int | None = None,
    layer_difference: str | int | None = None,
    path_precision: str | int | None = None,
) -> VectorizeOptions:
    """Build VTracer options from the GUI controls."""

    return VectorizeOptions(
        color_mode=cast(
            VectorizeColorMode,
            _choice(color_mode, _VECTORIZE_COLOR_MODES, "Color mode"),
        ),
        hierarchical=cast(
            VectorizeHierarchy,
            _choice(hierarchical, _VECTORIZE_HIERARCHIES, "Hierarchy"),
        ),
        curve_mode=cast(
            VectorizeCurveMode,
            _choice(curve_mode, _VECTORIZE_CURVE_MODES, "Curve mode"),
        ),
        filter_speckle=_optional_int(filter_speckle, "Filter speckle"),
        color_precision=_optional_int(color_precision, "Color precision"),
        layer_difference=_optional_int(layer_difference, "Layer difference"),
        path_precision=_optional_int(path_precision, "Path precision"),
    )


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
        self.root.minsize(560, 680)
        self.translations = load_translations()
        self.locale = DEFAULT_LOCALE
        self._events: Queue[_GuiEvent] = Queue()
        self._cancel_event = Event()
        self._worker: Thread | None = None
        self._running = False

        initial_name = translation_for(self.locale, self.translations)["name"]
        self.language_var = tk.StringVar(value=initial_name)
        self.status_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="embed")
        self.output_dir_var = tk.StringVar()
        self.overwrite_var = tk.BooleanVar(value=False)
        self.recursive_var = tk.BooleanVar(value=False)

        self.max_width_var = tk.StringVar()
        self.max_height_var = tk.StringVar()
        self.jpeg_quality_var = tk.StringVar()
        self.png_compress_level_var = tk.StringVar()
        self.optimize_png_var = tk.BooleanVar(value=False)

        self.color_mode_var = tk.StringVar(value="color")
        self.hierarchical_var = tk.StringVar(value="stacked")
        self.curve_mode_var = tk.StringVar(value="spline")
        self.filter_speckle_var = tk.StringVar()
        self.color_precision_var = tk.StringVar()
        self.layer_difference_var = tk.StringVar()
        self.path_precision_var = tk.StringVar()

        controls = ttk.Frame(self.root, padding=20)
        controls.pack(fill=tk.BOTH, expand=True)

        self.mode_frame = ttk.LabelFrame(controls)
        self.mode_frame.pack(fill=tk.X)
        self.mode_label = ttk.Label(self.mode_frame)
        self.mode_label.grid(row=0, column=0, padx=(10, 4), pady=8, sticky=tk.W)
        self.embed_mode_button = ttk.Radiobutton(
            self.mode_frame,
            variable=self.mode_var,
            value="embed",
            command=self._update_option_state,
        )
        self.embed_mode_button.grid(row=0, column=1, padx=4, pady=8, sticky=tk.W)
        self.vectorize_mode_button = ttk.Radiobutton(
            self.mode_frame,
            variable=self.mode_var,
            value="vectorize",
            command=self._update_option_state,
        )
        self.vectorize_mode_button.grid(
            row=0, column=2, padx=(4, 10), pady=8, sticky=tk.W
        )

        self.output_frame = ttk.LabelFrame(controls)
        self.output_frame.pack(fill=tk.X, pady=(10, 0))
        self.output_frame.columnconfigure(1, weight=1)
        self.output_dir_label = ttk.Label(self.output_frame)
        self.output_dir_label.grid(
            row=0, column=0, padx=(10, 6), pady=(8, 2), sticky=tk.W
        )
        self.output_dir_entry = ttk.Entry(
            self.output_frame, textvariable=self.output_dir_var
        )
        self.output_dir_entry.grid(row=0, column=1, padx=4, pady=(8, 2), sticky=tk.EW)
        self.output_dir_button = ttk.Button(
            self.output_frame, command=self.select_output_directory
        )
        self.output_dir_button.grid(
            row=0, column=2, padx=(4, 10), pady=(8, 2), sticky=tk.E
        )
        self.output_dir_hint = ttk.Label(self.output_frame, wraplength=500)
        self.output_dir_hint.grid(
            row=1, column=0, columnspan=3, padx=10, pady=(0, 8), sticky=tk.W
        )

        self.general_options_frame = ttk.LabelFrame(controls)
        self.general_options_frame.pack(fill=tk.X, pady=(10, 0))
        self.overwrite_checkbutton = ttk.Checkbutton(
            self.general_options_frame, variable=self.overwrite_var
        )
        self.overwrite_checkbutton.grid(
            row=0, column=0, padx=(10, 8), pady=8, sticky=tk.W
        )
        self.recursive_checkbutton = ttk.Checkbutton(
            self.general_options_frame, variable=self.recursive_var
        )
        self.recursive_checkbutton.grid(
            row=0, column=1, padx=(8, 10), pady=8, sticky=tk.W
        )

        self.mode_options_frame = ttk.Frame(controls)
        self.mode_options_frame.pack(fill=tk.X, pady=(10, 0))
        self.embed_options_frame = ttk.LabelFrame(self.mode_options_frame)
        self.embed_options_frame.pack(fill=tk.X)
        self.embed_options_frame.columnconfigure(1, weight=1)
        self.max_width_label, self.max_width_entry = self._add_entry_control(
            self.embed_options_frame, 0, self.max_width_var
        )
        self.max_height_label, self.max_height_entry = self._add_entry_control(
            self.embed_options_frame, 1, self.max_height_var
        )
        self.jpeg_quality_label, self.jpeg_quality_entry = self._add_entry_control(
            self.embed_options_frame, 2, self.jpeg_quality_var
        )
        (
            self.png_compress_level_label,
            self.png_compress_level_entry,
        ) = self._add_entry_control(
            self.embed_options_frame, 3, self.png_compress_level_var
        )
        self.optimize_png_checkbutton = ttk.Checkbutton(
            self.embed_options_frame, variable=self.optimize_png_var
        )
        self.optimize_png_checkbutton.grid(
            row=4, column=0, columnspan=2, padx=10, pady=(4, 2), sticky=tk.W
        )
        self.embed_options_hint = ttk.Label(self.embed_options_frame, wraplength=500)
        self.embed_options_hint.grid(
            row=5, column=0, columnspan=2, padx=10, pady=(0, 8), sticky=tk.W
        )
        self._embed_widgets = [
            self.max_width_entry,
            self.max_height_entry,
            self.jpeg_quality_entry,
            self.png_compress_level_entry,
            self.optimize_png_checkbutton,
        ]

        self.vectorize_options_frame = ttk.LabelFrame(self.mode_options_frame)
        self.vectorize_options_frame.pack(fill=tk.X)
        self.vectorize_options_frame.columnconfigure(1, weight=1)
        self.color_mode_label, self.color_mode_menu = self._add_choice_control(
            self.vectorize_options_frame,
            0,
            self.color_mode_var,
            _VECTORIZE_COLOR_MODES,
        )
        self.hierarchical_label, self.hierarchical_menu = self._add_choice_control(
            self.vectorize_options_frame,
            1,
            self.hierarchical_var,
            _VECTORIZE_HIERARCHIES,
        )
        self.curve_mode_label, self.curve_mode_menu = self._add_choice_control(
            self.vectorize_options_frame,
            2,
            self.curve_mode_var,
            _VECTORIZE_CURVE_MODES,
        )
        self.filter_speckle_label, self.filter_speckle_entry = self._add_entry_control(
            self.vectorize_options_frame, 3, self.filter_speckle_var
        )
        self.color_precision_label, self.color_precision_entry = (
            self._add_entry_control(
                self.vectorize_options_frame, 4, self.color_precision_var
            )
        )
        self.layer_difference_label, self.layer_difference_entry = (
            self._add_entry_control(
                self.vectorize_options_frame, 5, self.layer_difference_var
            )
        )
        self.path_precision_label, self.path_precision_entry = self._add_entry_control(
            self.vectorize_options_frame, 6, self.path_precision_var
        )
        self.vectorize_options_hint = ttk.Label(
            self.vectorize_options_frame, wraplength=500
        )
        self.vectorize_options_hint.grid(
            row=7, column=0, columnspan=2, padx=10, pady=(0, 8), sticky=tk.W
        )
        self._vectorize_choice_widgets = [
            self.color_mode_menu,
            self.hierarchical_menu,
            self.curve_mode_menu,
        ]
        self._vectorize_entry_widgets = [
            self.filter_speckle_entry,
            self.color_precision_entry,
            self.layer_difference_entry,
            self.path_precision_entry,
        ]

        actions = ttk.Frame(controls)
        actions.pack(fill=tk.X, pady=(14, 0))
        self.files_button = ttk.Button(actions, command=self.select_files)
        self.files_button.pack(fill=tk.X)
        self.folder_button = ttk.Button(actions, command=self.select_folder)
        self.folder_button.pack(fill=tk.X, pady=(8, 0))
        self.cancel_button = ttk.Button(
            actions, command=self.cancel_conversion, state=tk.DISABLED
        )
        self.cancel_button.pack(fill=tk.X, pady=(8, 0))
        self.progress = ttk.Progressbar(controls, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(16, 0))
        self.status = ttk.Label(controls, textvariable=self.status_var, wraplength=500)
        self.status.pack(fill=tk.X, pady=(8, 0))

        self._always_enabled_settings = [
            self.embed_mode_button,
            self.vectorize_mode_button,
            self.output_dir_entry,
            self.output_dir_button,
            self.overwrite_checkbutton,
            self.recursive_checkbutton,
        ]
        self._settings_widgets = [
            *self._always_enabled_settings,
            *self._embed_widgets,
            *self._vectorize_choice_widgets,
            *self._vectorize_entry_widgets,
        ]

        self.language_menu = tk.OptionMenu(
            controls,
            self.language_var,
            *(text["name"] for text in self.translations.values()),
            command=self.change_language,
        )
        self.language_menu.pack(fill=tk.X, pady=(16, 0))
        self._refresh_text()

    @staticmethod
    def _add_entry_control(
        parent: ttk.LabelFrame, row: int, variable: tk.StringVar
    ) -> tuple[ttk.Label, ttk.Entry]:
        label = ttk.Label(parent)
        label.grid(row=row, column=0, padx=(10, 6), pady=3, sticky=tk.W)
        entry = ttk.Entry(parent, textvariable=variable, width=14)
        entry.grid(row=row, column=1, padx=(4, 10), pady=3, sticky=tk.EW)
        return label, entry

    @staticmethod
    def _add_choice_control(
        parent: ttk.LabelFrame,
        row: int,
        variable: tk.StringVar,
        values: tuple[str, ...],
    ) -> tuple[ttk.Label, ttk.Combobox]:
        label = ttk.Label(parent)
        label.grid(row=row, column=0, padx=(10, 6), pady=3, sticky=tk.W)
        menu = ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            state="readonly",
            width=14,
        )
        menu.grid(row=row, column=1, padx=(4, 10), pady=3, sticky=tk.W)
        return label, menu

    @property
    def _text(self) -> dict[str, str]:
        return translation_for(self.locale, self.translations)

    def _refresh_text(self) -> None:
        text = self._text
        self.mode_frame.config(text=text["mode"])
        self.mode_label.config(text=text["mode"])
        self.embed_mode_button.config(text=text["embed_mode"])
        self.vectorize_mode_button.config(text=text["vectorize_mode"])
        self.output_frame.config(text=text["output_directory"])
        self.output_dir_label.config(text=text["output_directory"])
        self.output_dir_button.config(text=text["browse"])
        self.output_dir_hint.config(text=text["output_directory_hint"])
        self.general_options_frame.config(text=text["general_options"])
        self.overwrite_checkbutton.config(text=text["overwrite"])
        self.recursive_checkbutton.config(text=text["recursive"])
        self.embed_options_frame.config(text=text["embed_options"])
        self.max_width_label.config(text=text["max_width"])
        self.max_height_label.config(text=text["max_height"])
        self.jpeg_quality_label.config(text=text["jpeg_quality"])
        self.png_compress_level_label.config(text=text["png_compress_level"])
        self.optimize_png_checkbutton.config(text=text["optimize_png"])
        self.embed_options_hint.config(text=text["embed_options_hint"])
        self.vectorize_options_frame.config(text=text["vectorize_options"])
        self.color_mode_label.config(text=text["color_mode"])
        self.hierarchical_label.config(text=text["hierarchical"])
        self.curve_mode_label.config(text=text["curve_mode"])
        self.filter_speckle_label.config(text=text["filter_speckle"])
        self.color_precision_label.config(text=text["color_precision"])
        self.layer_difference_label.config(text=text["layer_difference"])
        self.path_precision_label.config(text=text["path_precision"])
        self.vectorize_options_hint.config(text=text["vectorize_options_hint"])
        self.files_button.config(text=text["select_files"])
        self.folder_button.config(text=text["select_folder"])
        self.cancel_button.config(text=text["cancel"])
        if not self._running:
            self.status_var.set(text["ready"])
        self._update_option_state()

    def _update_option_state(self) -> None:
        """Enable controls belonging to the selected conversion mode."""

        if self._running:
            return
        for widget in self._always_enabled_settings:
            widget.configure(state=tk.NORMAL)
        embed_enabled = self.mode_var.get() == "embed"
        if embed_enabled:
            self.vectorize_options_frame.pack_forget()
            self.embed_options_frame.pack(fill=tk.X)
        else:
            self.embed_options_frame.pack_forget()
            self.vectorize_options_frame.pack(fill=tk.X)
        for widget in self._embed_widgets:
            widget.configure(state=tk.NORMAL if embed_enabled else tk.DISABLED)
        for widget in self._vectorize_entry_widgets:
            widget.configure(state=tk.DISABLED if embed_enabled else tk.NORMAL)
        for widget in self._vectorize_choice_widgets:
            widget.configure(state=tk.DISABLED if embed_enabled else "readonly")

    def _build_conversion_options(self) -> GuiConversionOptions:
        """Validate visible controls and return an immutable conversion snapshot."""

        mode_value = self.mode_var.get()
        output_dir = self.output_dir_var.get().strip() or None
        if mode_value == "embed":
            return GuiConversionOptions(
                mode=cast(ConversionMode, mode_value),
                output_dir=output_dir,
                overwrite=bool(self.overwrite_var.get()),
                recursive=bool(self.recursive_var.get()),
                embed_options=build_embed_options(
                    max_width=self.max_width_var.get(),
                    max_height=self.max_height_var.get(),
                    jpeg_quality=self.jpeg_quality_var.get(),
                    png_compress_level=self.png_compress_level_var.get(),
                    optimize_png=bool(self.optimize_png_var.get()),
                ),
                vectorize_options=None,
            )
        if mode_value != "vectorize":
            raise ValueError("Mode must be either embed or vectorize.")
        return GuiConversionOptions(
            mode=cast(ConversionMode, mode_value),
            output_dir=output_dir,
            overwrite=bool(self.overwrite_var.get()),
            recursive=bool(self.recursive_var.get()),
            embed_options=None,
            vectorize_options=build_vectorize_options(
                color_mode=self.color_mode_var.get(),
                hierarchical=self.hierarchical_var.get(),
                curve_mode=self.curve_mode_var.get(),
                filter_speckle=self.filter_speckle_var.get(),
                color_precision=self.color_precision_var.get(),
                layer_difference=self.layer_difference_var.get(),
                path_precision=self.path_precision_var.get(),
            ),
        )

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

    def select_output_directory(self) -> None:
        """Choose where generated SVG files should be written."""

        folder = filedialog.askdirectory(
            parent=self.root, title=self._text["output_directory"]
        )
        if folder:
            self.output_dir_var.set(folder)

    def _start_conversion(self, input_paths: tuple[str, ...] | list[str]) -> None:
        try:
            options = self._build_conversion_options()
        except ValueError as error:
            self.status_var.set(self._text["invalid_options"])
            messagebox.showerror(
                self._text["invalid_options_title"], str(error), parent=self.root
            )
            return

        self._cancel_event.clear()
        self._set_running(True)
        self.progress.configure(value=0, maximum=1)
        self.status_var.set(self._text["starting"])
        self._worker = Thread(
            target=self._run_conversion,
            args=(input_paths, options),
            daemon=True,
        )
        self._worker.start()
        self.root.after(_POLL_INTERVAL_MS, self._poll_events)

    def _run_conversion(
        self,
        input_paths: tuple[str, ...] | list[str],
        options: GuiConversionOptions | None = None,
    ) -> None:
        try:
            conversion_options = (
                options
                if options is not None
                else GuiConversionOptions(
                    mode="embed",
                    output_dir=None,
                    overwrite=False,
                    recursive=False,
                    embed_options=None,
                    vectorize_options=None,
                )
            )
            result = convert_paths(
                input_paths,
                output_dir=conversion_options.output_dir,
                overwrite=conversion_options.overwrite,
                recursive=conversion_options.recursive,
                mode=conversion_options.mode,
                vectorize_options=conversion_options.vectorize_options,
                embed_options=conversion_options.embed_options,
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
        self._running = running
        state = tk.DISABLED if running else tk.NORMAL
        self.files_button.config(state=state)
        self.folder_button.config(state=state)
        self.cancel_button.config(state=tk.NORMAL if running else tk.DISABLED)
        if running:
            for widget in self._settings_widgets:
                widget.configure(state=tk.DISABLED)
        else:
            self._worker = None
            self._update_option_state()

    def cancel_conversion(self) -> None:
        """Request a clean stop after the image currently being processed."""

        self._cancel_event.set()
        self.cancel_button.config(state=tk.DISABLED)
        self.status_var.set(self._text["cancelling"])

    def change_language(self, display_name: str | tk.StringVar) -> None:
        selected_name = (
            display_name.get()
            if isinstance(display_name, tk.StringVar)
            else display_name
        )
        self.locale = locale_for_display_name(selected_name, self.translations)
        self._refresh_text()

    def run(self) -> None:
        """Start the Tkinter event loop."""

        self.root.mainloop()


def run_gui() -> None:
    """Launch the SVGConverter desktop interface."""

    SVGConverterApp().run()
