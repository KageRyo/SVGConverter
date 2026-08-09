# SVGConverter

[English](README.md)

SVGConverter 會將 PNG 或 JPEG 影像包裝到 SVG 容器中，並提供 Python API、命令列工具與桌面 GUI。

> **重要：**目前的 `embed` 模式是把原始點陣影像 Base64 編碼後放進 SVG 的 `<image>`
> 元素。它**不會**把像素描繪成向量路徑，也不會因為包進 SVG 就自然縮小檔案。真正的
> `vectorize` 模式會在後續版本另行提供。

## 安裝

SVGConverter 需要 Python 3.10 以上。v1.2.0 發布到 PyPI 後可使用：

```bash
python -m pip install --upgrade svgconverter
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
```

轉換資料夾最外層的所有支援影像：

```bash
svgconverter ./images --output-dir ./svg-output
```

除非指定 `--overwrite`，既有輸出檔不會被覆寫。使用 `svgconverter --help` 可查看完整選項。
目前支援 PNG、JPG、JPEG（含大寫副檔名）；遞迴轉換與影像最佳化尚未包含在此版本。

## Python API

```python
from svgconverter import SVGConverter, convert_file

convert_file("image.png", "image.svg")

converter = SVGConverter(overwrite=True)
result = converter.convert_directory("./images", "./svg-output")
print(result.success_count, result.failure_count)
```

`convert_file()` 會回傳輸出 `pathlib.Path`。資料夾轉換則回傳 `BatchResult`，其中包含成功檔案與
逐檔錯誤，單一壞檔不會使整批工作中斷。

## GUI

安裝套件後執行：

```bash
svgconverter-gui
```

開發環境仍可用 `python main.py` 啟動相同 GUI。目前 GUI 以資料夾為單位轉換，並支援正體中文、
English、日文；它與命令列共用同一套公開轉換 API。

## 發布流程

標籤發布使用 [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)，不保存長期
PyPI API token。第一次發布前，請在 PyPI 設定 pending 或 normal Trusted Publisher：

- owner：`KageRyo`
- repository：`SVGConverter`
- workflow：`release.yml`
- environment：`pypi`

PR 合併後，建立與 `pyproject.toml` 版本一致的註解標籤 `v1.2.0`。工作流程會建置、檢查、發布到
PyPI，成功後才建立並附上 distributions 的 GitHub Release。

## 貢獻與授權

本機檢查與提交格式請見 [CONTRIBUTING.md](CONTRIBUTING.md)。本專案採用 [MIT License](LICENSE)。
