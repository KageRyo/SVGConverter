"""Tkinter desktop interface built on the public conversion API."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox

from .converter import SVGConverter, SVGConverterError
from .i18n import (
    DEFAULT_LOCALE,
    load_translations,
    locale_for_display_name,
    translation_for,
)


class SVGConverterApp:
    """The standalone GUI application."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("SVGConverter")
        self.converter = SVGConverter()
        self.translations = load_translations()
        self.locale = DEFAULT_LOCALE
        self.button = tk.Button(self.root, command=self.select_folder)
        self.button.pack(pady=20)
        initial_name = translation_for(self.locale, self.translations)["name"]
        self.language_var = tk.StringVar(value=initial_name)
        self.language_menu = tk.OptionMenu(
            self.root,
            self.language_var,
            *(text["name"] for text in self.translations.values()),
            command=self.change_language,
        )
        self.language_menu.pack()
        self._refresh_text()

    def _refresh_text(self) -> None:
        self.button.config(
            text=translation_for(self.locale, self.translations)["select"]
        )

    def select_folder(self) -> None:
        folder = filedialog.askdirectory(parent=self.root)
        if not folder:
            return
        text = translation_for(self.locale, self.translations)
        try:
            result = self.converter.convert_directory(folder)
        except SVGConverterError as error:
            messagebox.showerror("SVGConverter", str(error), parent=self.root)
            return

        message = text["done"].format(
            converted=result.success_count, failed=result.failure_count
        )
        if result.failed:
            details = "\n".join(
                f"{failure.input_path.name}: {failure.error}"
                for failure in result.failed
            )
            messagebox.showwarning(
                "SVGConverter", f"{message}\n\n{details}", parent=self.root
            )
        else:
            messagebox.showinfo("SVGConverter", message, parent=self.root)

    def change_language(self, display_name: str) -> None:
        self.locale = locale_for_display_name(display_name, self.translations)
        self._refresh_text()

    def run(self) -> None:
        """Start the Tkinter event loop."""

        self.root.mainloop()


def run_gui() -> None:
    """Launch the SVGConverter desktop interface."""

    SVGConverterApp().run()
