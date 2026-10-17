# CLI JSON 報告

在單檔或批次指令加上 `--json`，標準輸出只會寫入一個 JSON 物件與換行，
不會混入轉換進度或文字摘要。JSON 使用 Unicode escape，因此即使終端機不是
UTF-8，解析後仍能還原中文路徑。不指定 `--json` 時，原有文字輸出與轉換行為維持不變。

```bash
svgconverter 'images/圖示.png' --output 'svg-output/圖示.svg' --json
svgconverter ./images --output-dir ./svg-output --recursive --json
```

## Schema 版本 1

`schema_version` 是整數 `1`。使用端應檢查版本並忽略不認識的欄位。
版本 1 可以新增欄位；移除、改名、變更欄位型別或計數語意時，必須使用新版本。
物件欄位順序與空白不屬於相容性契約。報告的欄位順序固定且不含時間戳；
逐檔陣列依轉換 API 處理順序排列（明確輸入依參數順序，資料夾內檔案依相對路徑
不分大小寫排序）。

每份報告都有下列欄位：

| 欄位 | 型別 | 意義 |
| --- | --- | --- |
| `schema_version` | 整數 | 報告 schema 版本，目前為 `1`。 |
| `inputs` | 字串陣列 | 請求的檔案／資料夾路徑，經 `pathlib.Path` 解析。 |
| `output` | 字串或 null | 明確指定的 `--output` 路徑；未指定時為 null。 |
| `output_dir` | 字串或 null | 明確指定的 `--output-dir` 路徑；未指定時為 null。 |
| `mode` | 字串 | `embed` 或 `vectorize`。 |
| `totals` | 物件 | 整數 `converted`、`skipped`、`failed`，與各陣列長度一致。 |
| `converted` | 物件陣列 | 成功項目，含 `input_path`、`output_path`、`input_bytes`、`svg_bytes`、`embedded_raster_bytes`。 |
| `skipped` | 物件陣列 | 未修改項目，含 `input_path`、`output_path` 與字串 `reason`。 |
| `failed` | 物件陣列 | 逐檔失敗，含 `input_path`、字串 `error` 與字串 `error_type`。 |
| `cancelled` | 布林 | 轉換 API 是否回傳已取消的結果。 |
| `sizes` | 物件 | 僅加總成功項目的 `input_bytes`、`svg_bytes`、`embedded_raster_bytes`。 |
| `error` | 物件或 null | 整體操作失敗，含字串 `error` 與 `error_type`；未發生時為 null。 |

路徑採主機平台格式。結果路徑沿用 Python API 規則：相對路徑仍為相對路徑，
指定 `--allowed-root` 時才解析路徑。`output` 或 `output_dir` 為 null 不代表沒有輸出：
成功／略過項目會列出實際目的路徑。失敗項目沒有成功輸出，因此只列來源與錯誤，不猜測目的路徑。

Byte 大小為非負整數。Vectorize 項目的 `embedded_raster_bytes` 為 null；
沒有嵌入點陣的總計也為 null。空批次、全部略過或全部失敗的批次，輸入與 SVG byte
總計為零，成功陣列為空，並回報對應計數。資料夾內不支援的副檔名沿用原有批次政策直接忽略，
不計入略過數量。

單一壞檔與批次壞檔一樣列入 `failed`。找不到輸入資料夾、輸出資料夾無效等使整批
無法開始規劃的問題列於 `error`；因未處理任何檔案，逐檔陣列保持空白、計數為零。
錯誤訊息與略過原因是供人閱讀的文字，日後可能調整；自動化應依結束代碼與
`error_type` 分類判斷，不應比對訊息文字。

## 結束代碼與 shell 自動化

- `0`：轉換成功、空批次或僅有略過。
- `1`：至少一個逐檔失敗、整體操作錯誤或結果已取消。仍會輸出 JSON 報告。
- `2`：命令參數無效，包含未知旗標、無效選項值，以及對資料夾使用 `--output` 等
  無效組合。診斷會寫入標準錯誤；即使指定 `--json`，標準輸出仍為空。

`--help` 與 `--version` 保留原有文字輸出與結束代碼 `0`。
CLI 目前沒有取消選項；Ctrl+C 等外部中斷不保證能產生完整 JSON 報告。

以下 shell 腳本使用 `jq`，即使批次部分失敗仍可檢視報告，並保留轉換指令的結束代碼：

```bash
status=0
svgconverter ./images --output-dir ./svg-output --json > report.json || status=$?
if [ "$status" -le 1 ]; then
    jq '{totals, failed, error}' report.json
fi
exit "$status"
```
