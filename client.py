import tkinter as tk
from tkinter import filedialog, messagebox
from converter import ImageToSVGConverter

class ImageToSVGConverterUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SVGConverter")

        self.converter = ImageToSVGConverter()

        self.select_folder_button = tk.Button(self.root, text="選擇圖片所在的資料夾", command=self.select_folder)
        self.select_folder_button.pack(pady=20)

    def select_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.converter.convert_images_in_folder(folder_path)
            messagebox.showinfo("轉檔完成", "所有資料夾中的圖片都轉成SVG了！")

    def run(self):
        self.root.mainloop()
