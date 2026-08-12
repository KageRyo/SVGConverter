# SVGConverter

[English](README.md)

SVGConverter 可將 PNG、JPEG、WebP、BMP、TIFF 影像轉為 SVG，並提供 Python API、
命令列工具與桌面 GUI。

## 轉換模式

- **`embed`**（預設）把原始點陣資料放進 SVG 的 `<image>` 元素，能保留來源像素；但它不是
  向量化，且 Base64 編碼可能讓輸出大於原圖。
- **`vectorize`** 使用選用的 [VTracer](https://github.com/visioncortex/vtracer) 後端，把
  點陣區域描繪為 SVG 路徑。它適合 logo、icon、插圖與高對比線稿；照片可能產生較大且風格化、
  不一定忠於原圖的結果。

## 安裝

SVGConverter 需要 Python 3.10 以上：

```bash
python -m pip install --upgrade svgconverter
```

需要實際向量化時，安裝額外相依：

```bash
python -m pip install --upgrade "svgconverter[vectorize]"
```

目前的開發版本可直接安裝：

```bash
git clone https://github.com/KageRyo/SVGConverter.git
cd SVGConverter
python -m pip install .
```

## 命令列

轉換單一檔案：

```bash
svgconverter image.png
svgconverter photo.jpg --output output.svg
svgconverter logo.png --mode vectorize --vectorize-color-mode binary
```

轉換資料夾最外層的所有支援影像：

```bash
svgconverter ./images --output-dir ./svg-output
```

遞迴轉換子資料夾，並在輸出資料夾中保留相對路徑：

```bash
svgconverter ./images --output-dir ./svg-output --recursive
```

一次轉換多個明確指定的檔案；支援萬用字元展開的 shell 也可以在執行前展開
`./images/*.png` 這類 pattern：

```bash
svgconverter image.png photo.jpg --output-dir ./svg-output
```

批次轉換時，除非指定 `--overwrite`，既有 SVG 輸出檔會列為略過；最後摘要會列出
轉換成功、略過與失敗數量。目前支援 PNG、JPG、JPEG、WebP、BMP、TIF、TIFF（含大寫副檔名）。
使用 `svgconverter --help` 可查看完整選項。`vectorize` 模式需要安裝選用的
`vectorize` extra。

## Python API

```python
from svgconverter import SVGConverter, convert_file, convert_paths

convert_file("image.png", "image.svg")
convert_file("logo.png", "logo.svg", mode="vectorize")

converter = SVGConverter(overwrite=True)
result = converter.convert_directory("./images", "./svg-output", recursive=True)
batch = convert_paths(["logo.png", "photo.jpg"], "./svg-output")
print(result.success_count, result.skipped_count, result.failure_count)
```

`convert_file()` 會回傳輸出 `pathlib.Path`。資料夾轉換則回傳 `BatchResult`，其中包含成功檔案與
逐檔錯誤，單一壞檔不會使整批工作中斷。`convert_paths()` 可接收檔案與資料夾的混合輸入；
批次既有輸出預設列為略過，指定 `overwrite=True` 才會覆寫。

## GUI

安裝套件後執行：

```bash
svgconverter-gui
```

開發環境仍可用 `python main.py` 啟動相同 GUI。目前 GUI 以資料夾為單位轉換，並支援正體中文、
English、日文；目前 GUI 使用 embed mode，`vectorize` 模式可從 Python API 與命令列使用。

## 貢獻與授權

本機檢查與提交格式請見 [CONTRIBUTING.md](CONTRIBUTING.md)。本專案採用 [MIT License](LICENSE)。
