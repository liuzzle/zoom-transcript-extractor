# Zoom Transcript Extractor

Extract transcript-like text from a saved Zoom recording player HTML page.

This repository contains a small Python script that scans a Zoom HTML export and pulls out likely transcript/caption lines, optionally with timestamps.

## Features

- Works on saved Zoom recording player HTML files.
- Uses multiple extraction strategies:
  - Transcript/caption-like HTML elements
  - JSON-like snippets containing text and time fields
  - Embedded JSON payloads inside script tags
- Decodes HTML entities and escaped unicode sequences.
- Removes duplicate lines while preserving original order.
- Filters common non-transcript boilerplate text.
- Writes results to a plain text file.

## Repository Structure

- `extract_zoom_transcript.py`: Main extraction script.
- `audio_transcript.html`: Example/source HTML file.
- `transcript.txt`: Example extracted transcript output.
- `transcript_clean.txt`: Cleaned transcript text sample.

## Requirements

- Python 3.9+ (recommended)
- No third-party dependencies (uses only Python standard library)

## Quick Start

1. Save the Zoom recording page HTML after opening the transcript panel.
2. Run the script:

```bash
python extract_zoom_transcript.py audio_transcript.html -o transcript_extracted.txt
```

3. Open the output text file.

## Usage

```bash
python extract_zoom_transcript.py INPUT_HTML -o OUTPUT_TXT
```

### Arguments

- `INPUT_HTML`: Path to the saved Zoom recording HTML page.
- `-o, --output`: Output text file path.
  - Default: `transcript_extracted.txt`

### Examples

Use default output filename:

```bash
python extract_zoom_transcript.py audio_transcript.html
```

Specify a custom output filename:

```bash
python extract_zoom_transcript.py audio_transcript.html -o transcript.txt
```

## How It Works

The extractor combines three heuristics:

1. Tag-based extraction: Finds elements whose `id` or `class` suggests transcript/captions.
2. JSON-like object extraction: Finds small text objects that may include time metadata.
3. Embedded JSON parsing: Scans script blocks for parseable JSON that contains transcript-like fields.

Then it performs final cleanup:

- Normalizes whitespace
- Removes exact duplicates (stable order)
- Filters obvious UI boilerplate (for example, cookie/privacy strings)

## Troubleshooting

### No transcript lines found

If you see this message:

"No transcript-like elements found. Save the page after opening the transcript panel in Zoom, then try again."

Try the following:

- Open the transcript panel in Zoom before saving the HTML page.
- Re-save the page after transcript content is visible.
- Confirm the input file path is correct.

### Encoding issues

The script reads input as UTF-8 with `errors="ignore"` and attempts to decode escaped unicode values, which handles most export variations.

## Notes

- This tool is heuristic-based and depends on Zoom page structure.
- Different Zoom export versions may require small pattern updates over time.

