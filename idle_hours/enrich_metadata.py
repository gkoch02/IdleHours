#!/usr/bin/env python3
"""Enrich corpus rows with title/author metadata parsed from Gutenberg headers."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from idle_hours import atomic_io
from idle_hours.jsonl_io import iter_jsonl

BASE_DIR = Path(__file__).resolve().parent


HEADER_SCAN_LINES = 120

# Gutenberg renders authors in Library-of-Congress form, which prepends lowercase
# nobility titles to the name (e.g. "graf Leo Tolstoy" for Leo Tolstoy). Strip
# them so the display metadata reads naturally.
_LEADING_TITLE_PREFIXES = ("graf ",)

# Exact-string fixups for Gutenberg headers that are malformed (duplicated
# surname) or incomplete (missing first name) in ways no generic rule can
# repair. Key = header as-written, value = preferred display form.
_AUTHOR_FIXUPS = {
    "Baroness Emmuska Orczy Orczy": "Baroness Emmuska Orczy",
    "Mrs. Rowson": "Susanna Rowson",
}


# A catalogue expansion of the initials: "H. C. (Herman Cyril) McNeile".
_AUTHOR_EXPANSION = re.compile(r"\s*\([^)]*\)")


def clean_author(author: str) -> str:
    if author in _AUTHOR_FIXUPS:
        return _AUTHOR_FIXUPS[author]
    author = " ".join(_AUTHOR_EXPANSION.sub("", author).split())
    lowered = author.lower()
    for prefix in _LEADING_TITLE_PREFIXES:
        if lowered.startswith(prefix):
            return author[len(prefix):].strip()
    return author


# Titles the generic rule gets wrong, keyed by the title it produces.
_TITLE_FIXUPS = {
    "A Christmas Carol in Prose": "A Christmas Carol",
    "Moby Dick": "Moby-Dick",
    # Gutenberg files The Singing Bone under its American title.
    "The Adventures of Dr. Thorndyke": "The Singing Bone",
}
_SUBTITLE = re.compile(r"\s*[:;]\s.*$")
_TRAILING_PARENTHETICAL = re.compile(r"\s*\([^)]*\)$")
_TITLE_QUOTES = "\"“”"
# Lower case inside a title, as the printed books set them.
_TITLE_SMALL_WORDS = frozenset(
    "a an the and but or nor for so yet as at by in of off on per to up via from into onto upon with de des du la le les von van".split()
)


def clean_title(title: str) -> str:
    """The title as a book's spine prints it, for attributions in little room.

    Gutenberg's catalogue form carries the subtitle ("Jane Eyre: An
    Autobiography", "The Manxman : a novel", "Moby Dick; Or, The Whale") and
    library sentence case ("The Maltese falcon"). The subtitle goes, and each
    word but the small ones is capitalised; a word with a capital already
    ("d'Urbervilles", "McTeague") is left as it is.
    """
    title = _TRAILING_PARENTHETICAL.sub("", _SUBTITLE.sub("", " ".join(title.split())))
    title = title.strip().strip(_TITLE_QUOTES).strip()
    words = title.split(" ")
    for i, word in enumerate(words):
        if not word or any(ch.isupper() for ch in word):
            continue
        if i > 0 and word.lower() in _TITLE_SMALL_WORDS and not words[i - 1].endswith((":", "—")):
            continue
        words[i] = word[0].upper() + word[1:]
    title = " ".join(words)
    return _TITLE_FIXUPS.get(title, title)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add source metadata to corpus rows.")
    parser.add_argument("input", help="Input JSONL corpus file")
    parser.add_argument(
        "--output",
        default=str(BASE_DIR / "assets/candidates-attributed.jsonl"),
        help="Output JSONL path for the packaged runtime dataset",
    )
    parser.add_argument(
        "--gutenberg-dir",
        default="data/gutenberg",
        help="Directory containing cached Gutenberg texts",
    )
    return parser.parse_args()


def parse_header(path: Path) -> tuple[str | None, str | None]:
    title = None
    author = None
    if not path.exists():
        return title, author
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:HEADER_SCAN_LINES]:
        stripped = line.strip()
        if stripped.startswith("Title: ") and not title:
            title = stripped.replace("Title: ", "", 1).strip()
        elif stripped.startswith("Author: ") and not author:
            author = clean_author(stripped.replace("Author: ", "", 1).strip())
        if title and author:
            break
    return title, author


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    gutenberg_dir = Path(args.gutenberg_dir).expanduser()

    rows = []
    metadata_cache: dict[str, tuple[str | None, str | None]] = {}
    for row in iter_jsonl(input_path):
        source_id = row.get("source_id")
        title = row.get("title")
        author = row.get("author")
        if source_id and (not title or not author):
            if source_id not in metadata_cache:
                metadata_cache[source_id] = parse_header(gutenberg_dir / f"pg{source_id}.txt")
            parsed_title, parsed_author = metadata_cache[source_id]
            title = title or parsed_title
            author = author or parsed_author
        # Cleaned every pass, so rows enriched before a rule existed get it too.
        row["title"] = clean_title(title) if title else title
        row["author"] = clean_author(author) if author else author
        rows.append(row)

    atomic_io.atomic_write_lines(
        output_path, (json.dumps(row, ensure_ascii=False) for row in rows)
    )

    enriched = sum(1 for row in rows if row.get("title") or row.get("author"))
    print(f"Wrote {len(rows)} attributed rows to {output_path}")
    print(f"Rows with attribution metadata: {enriched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
