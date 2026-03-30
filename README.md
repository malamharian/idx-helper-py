# IDX Helper

A desktop app to download and aggregate financial reports from IDX (Indonesia Stock Exchange).

## Features

### Download

Fetch and download financial report files directly from the IDX API.

1. Select a **year** and **reporting period** (TW1 / TW2 / TW3 / Tahunan).
2. Optionally filter by **file type** (.xlsx, .pdf, .zip) or a **custom regex** pattern.
3. Optionally enter specific **emiten codes** (one per line) to limit the download. Leave blank to download all listed companies.
4. Click **Fetch Reports** to retrieve the list of available files.
5. Choose a **download directory**, then click **Start All** or start individual companies.

Downloads run concurrently and can be cancelled at any point. Use the **Concurrency** dropdown to control how many files download simultaneously (be careful to avoid rate limit. Defaults to 5).

### Aggregate

Merge all `.xlsx` files from a directory into a single spreadsheet, grouped by sheet name.

1. Pick an **input directory** containing the downloaded `.xlsx` files.
2. Pick an **output file** path for the merged result.
3. Click **Aggregate** to start. Each row in the output is prefixed with the source filename.

Sheets named `Context` and `InlineXBRL` are automatically excluded.

## Getting Started

Requires Python 3.10 - 3.12.

```bash
# Install dependencies
uv sync

# Run the app
uv run main.py
```

## Build Executable

```bash
uv run flet build windows --product "IDX Helper"
uv run flet build macos --product "IDX Helper"
```
