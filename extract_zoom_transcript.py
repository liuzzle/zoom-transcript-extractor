#!/usr/bin/env python3
"""
Extract transcript-like text from a Zoom recording player HTML export.

Usage:
  python extract_zoom_transcript.py recording.html -o transcript.txt
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Iterable


def decode_maybe_escaped(value: str) -> str:
    """Decode a string that may contain HTML entities and/or JavaScript-style unicode escapes."""
    # value may contain HTML entities (e.g. &amp;) and/or JavaScript unicode escapes (e.g. \u003c).
    value = html.unescape(value)
    # The unicode_escape codec will decode \uXXXX and \UXXXXXXXX sequences, as well as other backslash escapes.
    try:
        # Encode to bytes and decode with unicode_escape to handle JavaScript-style escapes.
        return bytes(value, "utf-8").decode("unicode_escape")
    # In case of malformed escape sequences, just return the unescaped value.
    except Exception:
        return value


def normalize_whitespace(text: str) -> str:
    """Collapse multiple whitespace characters into a single space, and trim leading/trailing whitespace."""
    return re.sub(r"\s+", " ", text).strip()


def strip_tags(raw_html: str) -> str:
    """Remove HTML tags from a string, leaving only the text content."""
    return normalize_whitespace(re.sub(r"<[^>]+>", " ", raw_html))


def unique_in_order(items: Iterable[str]) -> list[str]:
    """Return a list of unique items, preserving the original order."""
    # Use a set to track seen items and a list to preserve order.
    seen: set[str] = set()
    # initialize the output list
    out: list[str] = []
    # Iterate through items, adding unseen ones to the output list.
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def find_tag_transcript_candidates(page_html: str) -> list[str]:
    """Find elements that look like they might contain transcript text, based on their tag and attributes."""
    # Look for transcript/caption related IDs/classes.
    tag_re = re.compile(
        # Match tags that have id or class attributes containing transcript/caption-related keywords, and capture their inner text.
        r"<(?P<tag>\w+)[^>]*(?:id|class)=[\"'][^\"']*(?:transcript|caption|subtitles?|cc)[^\"']*[\"'][^>]*>(?P<body>.*?)</(?P=tag)>",
        re.IGNORECASE | re.DOTALL,
    )
    # Extract the text content from these tags, normalize whitespace, and filter out very short entries.
    hits = []
    for m in tag_re.finditer(page_html):
        text = strip_tags(m.group("body"))
        text = normalize_whitespace(text)
        if len(text) >= 8:
            hits.append(text)
    return unique_in_order(hits)


def find_json_text_time_candidates(page_html: str) -> list[str]:
    """Find small JSON-like objects that contain text fields and optional time fields, which may be part of the transcript data."""
    
    # Match small JSON-ish objects that include transcript-like text fields.
    text_key = r"(?:text|content|caption|transcript(?:Text)?|utterance|sentence|displayText)"
    time_key = r"(?:start(?:Time)?|start_time|time|timestamp|ts|offset)"

    # Look for JSON-like objects that contain a text field matching the above keys, and optionally a time field. Capture the text and time values.
    object_re = re.compile(
        rf"\{{[^{{}}]{{0,1200}}?\"{text_key}\"\s*:\s*\"(?P<txt>(?:\\.|[^\"\\]){{1,600}})\"[^{{}}]{{0,1200}}?\}}",
        re.IGNORECASE | re.DOTALL,
    )
    time_re = re.compile(
        rf"\"{time_key}\"\s*:\s*(?P<time>\"(?:\\.|[^\"\\])+\"|\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )

    # For each match, decode the text and time values, normalize whitespace, and format them as "[time] text" if a time is present.
    lines: list[str] = []
    for m in object_re.finditer(page_html):
        obj_str = m.group(0)
        txt = decode_maybe_escaped(m.group("txt"))
        txt = normalize_whitespace(txt)
        if not txt or len(txt) < 2:
            continue

        time_match = time_re.search(obj_str)
        if time_match:
            t_raw = time_match.group("time")
            if t_raw.startswith('"') and t_raw.endswith('"'):
                t_raw = decode_maybe_escaped(t_raw[1:-1])
            line = f"[{t_raw}] {txt}"
        else:
            line = txt
        lines.append(line)

    return unique_in_order(lines)


def seconds_to_hhmmss(value: float) -> str:
    """Convert a number of seconds (possibly fractional) to HH:MM:SS format."""
    total = int(round(value))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def try_parse_embedded_json(page_html: str) -> list[str]:
    """Some pages embed large JSON payloads in script tags, which may contain transcript data. Try to find and parse those."""
    # Some pages embed large JSON payloads in script tags.
    script_re = re.compile(r"<script[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)
    lines: list[str] = []

    # For each script tag, check if it contains transcript-related keywords. If so, try to parse any JSON objects/arrays in it and look for text/time fields.
    for script in script_re.findall(page_html):
        if not re.search(r"transcript|caption|subtitle|cc", script, re.IGNORECASE):
            continue

        # Pull out probable JSON arrays/objects assigned in JS.
        for blob in re.findall(r"(\{.*\}|\[.*\])", script, re.DOTALL):
            blob = blob.strip().rstrip(";")
            if len(blob) < 2:
                continue
            try:
                data = json.loads(blob)
            except Exception:
                continue
            # Walk the parsed JSON data structure looking for text fields and optional time fields, using a stack to avoid recursion limits.
            stack = [data]
            while stack:
                # Pop the next item from the stack. 
                item = stack.pop()
                # If it's a dict, look for text fields and optional time fields, and add any nested dicts/lists to the stack.
                if isinstance(item, dict):
                    keys = {k.lower(): k for k in item.keys()}
                    text_field = None
                    # Look for a text field using various possible keys.
                    for k in ["text", "content", "caption", "transcript", "transcripttext", "utterance", "sentence", "displaytext"]:
                        if k in keys:
                            text_field = keys[k]
                            break
                    # If we found a text field, decode and normalize it, and look for an optional time field to format the line.
                    if text_field:
                        txt = normalize_whitespace(str(item[text_field]))
                        if txt:
                            t = None
                            for tk in ["start", "starttime", "start_time", "time", "timestamp", "ts", "offset"]:
                                if tk in keys:
                                    t = item[keys[tk]]
                                    break
                            if isinstance(t, (int, float)):
                                lines.append(f"[{seconds_to_hhmmss(float(t))}] {txt}")
                            elif t is not None:
                                lines.append(f"[{t}] {txt}")
                            else:
                                lines.append(txt)
                    # Add any nested dicts/lists to the stack to continue searching for text/time fields.
                    for v in item.values():
                        if isinstance(v, (dict, list)):
                            stack.append(v)
                # If it's a list, add any nested dicts/lists to the stack.
                elif isinstance(item, list):
                    for v in item:
                        if isinstance(v, (dict, list)):
                            stack.append(v)
    # Final deduplication of lines found in the embedded JSON blobs.
    return unique_in_order(lines)


def extract_transcript_lines(page_html: str) -> list[str]:
    """Extract lines of text that look like they might be part of the transcript, using multiple strategies."""
    lines: list[str] = []
    # Strategy 1: Look for tags with transcript/caption-related IDs/classes.
    lines.extend(find_tag_transcript_candidates(page_html))
    lines.extend(find_json_text_time_candidates(page_html))
    lines.extend(try_parse_embedded_json(page_html))

    # Final cleanup: filter out obvious non-transcript boilerplate.
    filtered = []
    for line in unique_in_order(lines):
        low = line.lower()
        # Filter out lines that contain common boilerplate phrases that are unlikely to be part of the transcript.
        if any(
            noise in low
            for noise in [
                "accept cookies",
                "decline cookies",
                "privacy statement",
                "skip to main content",
            ]
        ):
            continue
        filtered.append(line)
    return filtered


def main() -> int:
    """Main entry point: parse arguments, read the input HTML, extract transcript lines, and write them to the output file. """
    # Set up command-line argument parsing.
    parser = argparse.ArgumentParser(description="Extract transcript-like text from a Zoom HTML recording page export")
    # The input is the path to the saved HTML file of the Zoom recording page, which should be saved after opening the transcript panel in Zoom. 
    parser.add_argument("input_html", type=Path, help="Path to the saved Zoom recording HTML")
    # The output is a text file where the extracted transcript lines will be written. Default is "transcript_extracted.txt".
    parser.add_argument("-o", "--output", type=Path, default=Path("transcript_extracted.txt"), help="Output text file")
    # Parse the command-line arguments.
    args = parser.parse_args()

    # Check that the input file exists, and read its contents.
    if not args.input_html.exists():
        # If the input file doesn't exist, print an error message and exit.
        raise SystemExit(f"Input file not found: {args.input_html}")

    # Read the input HTML file 
    page_html = args.input_html.read_text(encoding="utf-8", errors="ignore")
    # Extract transcript lines
    lines = extract_transcript_lines(page_html)

    # If no lines were found, print a message suggesting to save the page after opening the transcript panel in Zoom, and exit.
    if not lines:
        raise SystemExit(
            "No transcript-like elements found. Save the page after opening the transcript panel in Zoom, then try again."
        )

    # Write the extracted lines to the output file, joined by newlines.
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} lines to {args.output}")
    # Return 0 to indicate successful completion.
    return 0

# If this script is run directly (as the main module), call the main() function and exit with its return code.
if __name__ == "__main__":
    raise SystemExit(main())
