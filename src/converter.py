import os
from PIL import Image
import svgwrite
import base64

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
        # 將原始圖檔嵌入 SVG 格式
        with open(path, 'rb') as f:
            img_data = f.read()
            data_uri = 'data:image/png;base64,' + base64.b64encode(img_data).decode('utf-8')
            dwg.add(dwg.image(href=str(data_uri), insert=(0, 0), size=(img.width, img.height)))
        # 儲存 SVG
        dwg.save()
