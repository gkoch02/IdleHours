#!/usr/bin/env python3
"""Convert targeted sparse-bucket hits into mergeable candidate rows."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from idle_hours import atomic_io
from idle_hours.buckets import DEFAULT_BUCKET_MINUTES, bucket_for_time
from idle_hours.gutenberg_time_miner import phrase_time
from idle_hours.jsonl_io import iter_jsonl

BASE_DIR = Path(__file__).resolve().parent


DAYPARTS = {
    0: "midnight",
    1: "night",
    2: "night",
    3: "night",
    4: "night",
    5: "dawn",
    6: "dawn",
    7: "morning",
    8: "morning",
    9: "morning",
    10: "morning",
    11: "morning",
    12: "noon",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert targeted sparse-bucket hits into candidate rows.")
    parser.add_argument("input", help="targeted-candidates.jsonl path")
    parser.add_argument(
        "--output",
        default="output/targeted-candidates-importable.jsonl",
        help="Output JSONL path",
    )
    return parser.parse_args()


def minute_for_bucket(bucket: str) -> tuple[int, int, str]:
    hour_part, state = bucket.split("_", 1)
    hour12 = int(hour_part[1:])
    minute = DEFAULT_BUCKET_MINUTES[state]
    return hour12, minute, state


def row_from_targeted(raw: dict) -> dict:
    """The candidate row for one targeted hit. Its time comes from the
    matched phrase when the phrase names one on its own; the search's bucket
    is only a fallback: a hit for a bucket's search can name another time,
    and "twenty minutes to two" once shipped at 1:25 (issue #466)."""
    resolved_bucket = raw["resolved_bucket"]
    hour12, minute, _state = minute_for_bucket(resolved_bucket)
    parsed = phrase_time(raw.get("matched_text") or "")
    if parsed is not None:
        hour12, minute = parsed
        resolved_bucket = bucket_for_time(f"{hour12:02d}:{minute:02d}")
    normalized_time = f"{hour12:02d}:{minute:02d}"
    daypart = DAYPARTS.get(hour12, "night")
    return {
        "source_path": raw.get("source_path"),
        "source_id": raw.get("source_id"),
        "match_type": "targeted_phrase",
        "matched_text": raw.get("matched_text"),
        "quote_text": raw.get("quote_text"),
        "context_text": raw.get("context_text"),
        "hour": hour12,
        "minute": minute,
        "normalized_time": normalized_time,
        "fuzzy_bucket": resolved_bucket,
        "daypart_bucket": daypart,
        "line_number": raw.get("line_number"),
        "match_start": raw.get("match_start"),
        "match_end": raw.get("match_end"),
        "search_phrase": raw.get("search_phrase"),
        "target_bucket": raw.get("target_bucket"),
        "resolved_bucket": resolved_bucket,
    }


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    rows = []
    for raw in iter_jsonl(input_path):
        rows.append(row_from_targeted(raw))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic (issue #306): a crash mid-write must not leave a truncated file,
    # least of all on an in-place rewrite of the input.
    atomic_io.atomic_write_lines(output_path, (json.dumps(row, ensure_ascii=False) for row in rows))
    print(f"Wrote {len(rows)} importable targeted hits to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
