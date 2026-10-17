# CLI JSON reports

Add `--json` to any single-file or batch command to write exactly one JSON object
and a newline to standard output. Conversion lines and human-readable summaries
are suppressed. Standard output uses JSON Unicode escapes, so paths round-trip
without requiring a UTF-8 terminal. Without `--json`, the existing text output
and conversion behavior are unchanged.

```bash
svgconverter 'images/圖示.png' --output 'svg-output/圖示.svg' --json
svgconverter ./images --output-dir ./svg-output --recursive --json
```

## Schema version 1

`schema_version` is the integer `1`. Consumers should check it and ignore unknown
fields. Additive fields may appear within version 1; removing or renaming a field,
changing a field's type, or changing the meaning of a count requires a new schema
version. Object key order and whitespace are not part of the contract. Reports
have deterministic key order and no timestamps; per-item arrays retain the
conversion API's processing order (explicit inputs in argument order, discovered
files sorted by relative path without regard to case).

Every report has these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | integer | Report schema version, currently `1`. |
| `inputs` | array of strings | Requested file/directory paths, as parsed by `pathlib.Path`. |
| `output` | string or null | Explicit `--output` path, or null when omitted. |
| `output_dir` | string or null | Explicit `--output-dir` path, or null when omitted. |
| `mode` | string | `embed` or `vectorize`. |
| `totals` | object | Integer `converted`, `skipped`, and `failed` counts matching the arrays. |
| `converted` | array of objects | Successful items with `input_path`, `output_path`, `input_bytes`, `svg_bytes`, and `embedded_raster_bytes`. |
| `skipped` | array of objects | Unmodified items with `input_path`, `output_path`, and a string `reason`. |
| `failed` | array of objects | Per-file failures with `input_path`, string `error`, and string `error_type`. |
| `cancelled` | boolean | Whether the conversion API returned a cancelled result. |
| `sizes` | object | Summed `input_bytes`, `svg_bytes`, and `embedded_raster_bytes` for successful conversions only. |
| `error` | object or null | Operation-level failure with string `error` and `error_type`, or null. |

Paths use the host platform's path syntax. Result paths follow the Python API:
relative paths remain relative unless `--allowed-root` resolves them. An omitted
`output` or `output_dir` does not imply missing output: each converted/skipped
item gives its actual destination. A failed item has no successful output and
therefore reports its source and error, without guessing a destination.

Byte sizes are nonnegative integers. `embedded_raster_bytes` is null for
vectorized items and for totals with no embedded rasters. Empty, entirely skipped,
and entirely failed batches report zero input/SVG bytes, empty success arrays,
and the appropriate counts. Unsupported extensions discovered in a directory
are ignored by the existing batch policy and are not counted as skips.

A corrupt single file appears in `failed`, just like a corrupt batch item.
Failures that prevent planning a batch, such as a missing input directory or an
invalid output directory, appear in `error`; item arrays and totals remain empty
and zero because no files were processed. Error messages and skip reasons are
human-readable and may change; automation should use the exit status and
`error_type` category rather than matching the message text.

## Exit status and shell automation

- `0`: successful conversion, an empty batch, or skips only.
- `1`: at least one per-file failure, an operation-level error, or a cancelled
  result. A JSON report is still written.
- `2`: invalid command arguments, including unknown flags, invalid option values,
  and invalid combinations such as `--output` for a directory. Diagnostics go to
  standard error, and standard output is empty, including with `--json`.

`--help` and `--version` retain their usual text output and exit status `0`.
The CLI currently has no cancellation option; an external interruption such as
Ctrl+C does not guarantee a completed JSON report.

For a shell script using `jq`, inspect reports even when a batch partly fails,
and preserve the converter's exit status:

```bash
status=0
svgconverter ./images --output-dir ./svg-output --json > report.json || status=$?
if [ "$status" -le 1 ]; then
    jq '{totals, failed, error}' report.json
fi
exit "$status"
```
