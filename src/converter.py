import os
from PIL import Image
import svgwrite

# 轉換圖片成 SVG 格式
class convToSvg:
    # 要轉換的檔案資料夾
    def convert(self, folder):
        for file in os.listdir(folder):
            if self.supportedImage(file):
                path = os.path.join(folder, file)
                self.convertToSvg(path)

    # 支援 PNG / JPG / JPEG
    def supportedImage(self, filename):
        return filename.endswith((".png", ".jpg", ".jpeg"))

    # 轉換成 SVG
    def convertToSvg(self, path):
        img = Image.open(path)
        svg_file = os.path.splitext(path)[0] + ".svg"
        dwg = svgwrite.Drawing(filename=svg_file, size=(img.width, img.height))
        dwg.add(dwg.image(path, insert=(
            0, 0), size=(img.width, img.height)))
        dwg.save()
