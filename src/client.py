import json
import tkinter as tk
from tkinter import filedialog, messagebox
from src.converter import convToSvg

# 使用者介面
class clientUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SVGConverter")  # 介面標題
        self.converter = convToSvg()
        self.language = "zh_TW"  # 預設語言(zh_TW 正體中文 / en_US English / ja_JP 日本語)

        # 語言選擇功能
        with open("languages.json", "r", encoding="utf-8") as file:
            self.texts = json.load(file)
        self.button = tk.Button(
            self.root, text=self.texts[self.language]["select"], command=self.selectFolder)
        self.button.pack(pady=20)
        self.language_var = tk.StringVar(value="正體中文")
        self.language_menu = tk.OptionMenu(
            self.root, self.language_var, *[data["name"] for data in self.texts.values()], command=self.changeLang)
        self.language_menu.pack()

    # 選擇資料夾
    def selectFolder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.converter.convert(folder)
            messagebox.showinfo(
                "", self.texts[self.language]["done"])

    # 切換語言
    def changeLang(self, *args):
        self.language = self.language_var.get()
        self.button.config(text=self.texts[self.language]["select"])

    # 啟動程式
    def run(self):
        self.root.mainloop()
