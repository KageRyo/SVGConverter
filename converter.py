import os
from PIL import Image
import svgwrite

class ImageToSVGConverter:
    def convert_images_in_folder(self, folder_path):
        for filename in os.listdir(folder_path):
            if self.is_supported_image(filename):
                image_path = os.path.join(folder_path, filename)
                self.convert_to_svg(image_path)

    def is_supported_image(self, filename):
        return filename.endswith((".png", ".jpg", ".jpeg"))

    def convert_to_svg(self, image_path):
        img = Image.open(image_path)
        svg_file = os.path.splitext(image_path)[0] + ".svg"
        dwg = svgwrite.Drawing(filename=svg_file, size=(img.width, img.height))
        dwg.add(dwg.image(image_path, insert=(0, 0), size=(img.width, img.height)))
        dwg.save()
