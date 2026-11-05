"""Fence the docs' cross-references against drift.

The rosters and tables a reader needs are fenced elsewhere
(``test_docs_theme_registry``, the font table, the preview check); this
module covers the plain prose pointers between them, which nothing else
reads. Two shapes are checked:

- **Markdown links** in every tracked ``.md`` file: a relative target must
  exist, and a ``#fragment`` into a Markdown file must name one of its
  headings (GitHub's slug rules) or an explicit ``<a id=...>`` anchor.
- **Section pointers** (``docs/themes.md § biomech``) in tracked source and
  docs: the named doc must exist and carry a heading, or a ``- `name``` theme
  entry, for every name after a ``§``. Every theme module's header points at
  its design notes this way.

``docs/decisions.md`` once sent readers to a "Match Types" section of
CLAUDE.md long after it had moved to docs/pipeline.md; a pointer in prose has
no other check. Each scan also fails if it finds nothing to check, so a change
to the patterns cannot retire the fence by matching nothing.
"""

from __future__ import annotations

import re
import subprocess
from functools import cache
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# ``[text](target)`` or ``[text](target "title")``, images included.
LINK_RE = re.compile(r"!?\[[^\]\n]*\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
HTML_ANCHOR_RE = re.compile(r"<a\s+(?:name|id)=\"([^\"]+)\"")
SECTION_RE = re.compile(r"\b(docs/[A-Za-z0-9_]+\.md) ?§ ?([A-Za-z0-9_]+)((?:, ?§ ?[A-Za-z0-9_]+)*)")
EXTRA_SECTION_RE = re.compile(r"§ ?([A-Za-z0-9_]+)")

# Where a section pointer may be written. ``data/`` holds Gutenberg texts,
# whose own "§ 19" references are not ours. This module is skipped by the
# scan: its docstrings and fixtures hold deliberately broken pointers.
SECTION_POINTER_ROOTS = ("idle_hours", "scripts", "tests", "docs", "ops", "README.md", "CLAUDE.md")
THIS_MODULE = Path(__file__).resolve()


def _tracked(*pathspecs: str) -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--", *pathspecs],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [REPO_ROOT / name for name in out.split("\0") if name and (REPO_ROOT / name).is_file()]


def _prose_lines(path: Path):
    """Yield ``(line_number, line)`` outside fenced code blocks, with inline code removed."""
    in_fence = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield number, INLINE_CODE_RE.sub("", line)


def github_slug(heading: str) -> str:
    """The anchor GitHub gives a heading: lower-case, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"<[^>]+>", "", heading).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


@cache
def anchors_in(path: Path) -> frozenset[str]:
    """Every fragment a link into ``path`` may name, duplicate headings suffixed ``-1``, ``-2``…"""
    found: set[str] = set()
    seen: dict[str, int] = {}
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        found.update(HTML_ANCHOR_RE.findall(line))
        match = HEADING_RE.match(line)
        if match:
            slug = github_slug(match.group(1))
            count = seen.get(slug, 0)
            seen[slug] = count + 1
            found.add(slug if count == 0 else f"{slug}-{count}")
    return frozenset(found)


def _is_external(target: str) -> bool:
    return bool(re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", target)) or target.startswith("//")


def broken_links(path: Path) -> tuple[int, list[str]]:
    """Return ``(links_checked, problems)`` for the relative links in one Markdown file."""
    checked = 0
    problems: list[str] = []
    rel = path.relative_to(REPO_ROOT)
    for number, line in _prose_lines(path):
        for match in LINK_RE.finditer(line):
            target = match.group(1).strip("<>")
            if _is_external(target):
                continue
            checked += 1
            file_part, _, fragment = target.partition("#")
            resolved = (path.parent / file_part).resolve() if file_part else path
            if not resolved.exists():
                problems.append(f"{rel}:{number}: link target {target!r} does not exist")
            elif fragment and resolved.suffix == ".md" and fragment not in anchors_in(resolved):
                problems.append(f"{rel}:{number}: {target!r} names no heading in {resolved.relative_to(REPO_ROOT)}")
    return checked, problems


def section_exists(doc_text: str, name: str) -> bool:
    """True if ``doc_text`` has a heading naming ``name`` or a ``- `name``` entry (the themes.md shape)."""
    escaped = re.escape(name)
    return bool(re.search(rf"^\s*- `{escaped}`|^#{{1,6}} .*\b{escaped}\b", doc_text, re.MULTILINE | re.IGNORECASE))


def broken_section_pointers(path: Path) -> tuple[int, list[str]]:
    """Return ``(pointers_checked, problems)`` for the ``docs/x.md § name`` pointers in one file."""
    checked = 0
    problems: list[str] = []
    rel = path.relative_to(REPO_ROOT)
    for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        for match in SECTION_RE.finditer(line):
            doc = REPO_ROOT / match.group(1)
            names = [match.group(2), *EXTRA_SECTION_RE.findall(match.group(3))]
            checked += len(names)
            if not doc.is_file():
                problems.append(f"{rel}:{number}: {match.group(1)} does not exist")
                continue
            text = doc.read_text(encoding="utf-8")
            problems.extend(
                f"{rel}:{number}: {match.group(1)} has no section for {name!r}"
                for name in names
                if not section_exists(text, name)
            )
    return checked, problems


class TestGithubSlug:
    @pytest.mark.parametrize(
        "heading, slug",
        [
            ("Match Types", "match-types"),
            ("Rendering (`render_quote.py`)", "rendering-render_quotepy"),
            ("Rendering & themes", "rendering--themes"),
            ("Pi setup: step 2", "pi-setup-step-2"),
        ],
    )
    def test_matches_github(self, heading, slug):
        assert github_slug(heading) == slug

    def test_duplicate_headings_are_suffixed(self, tmp_path):
        doc = tmp_path / "dup.md"
        doc.write_text("# Notes\n\n## Notes\n\n```\n# not a heading\n```\n", encoding="utf-8")
        assert anchors_in(doc) == {"notes", "notes-1"}


class TestCheckerCatchesBreakage:
    """The checkers must fail on the shapes they exist to catch, or the fences below prove nothing."""

    def test_missing_file_and_missing_anchor(self, tmp_path, monkeypatch):
        monkeypatch.setattr(f"{__name__}.REPO_ROOT", tmp_path)
        (tmp_path / "target.md").write_text("# Real heading\n", encoding="utf-8")
        source = tmp_path / "source.md"
        source.write_text(
            "[ok](target.md#real-heading) [gone](nowhere.md) [stale](target.md#old-heading)"
            " [web](https://example.com/x.md) `[code](ignored.md)`\n",
            encoding="utf-8",
        )
        checked, problems = broken_links(source)
        assert checked == 3
        assert len(problems) == 2
        assert "nowhere.md" in problems[0] and "old-heading" in problems[1]

    def test_missing_section(self, tmp_path, monkeypatch):
        monkeypatch.setattr(f"{__name__}.REPO_ROOT", tmp_path)
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "themes.md").write_text("## Intro\n\n  - `biomech` (wall) — notes.\n", encoding="utf-8")
        source = tmp_path / "mod.py"
        source.write_text('"""Design notes: docs/themes.md § biomech, § retired_theme"""\n', encoding="utf-8")
        checked, problems = broken_section_pointers(source)
        assert checked == 2
        assert problems == ["mod.py:1: docs/themes.md has no section for 'retired_theme'"]


class TestRepoDocs:
    def test_markdown_links_resolve(self):
        files = _tracked("*.md")
        assert files, "no tracked Markdown files found"
        total = 0
        problems: list[str] = []
        for path in files:
            checked, found = broken_links(path)
            total += checked
            problems.extend(found)
        assert total, "no relative Markdown links found: LINK_RE no longer matches the docs"
        assert not problems, "broken doc links:\n  " + "\n  ".join(problems)

    def test_section_pointers_resolve(self):
        files = _tracked(*SECTION_POINTER_ROOTS)
        total = 0
        problems: list[str] = []
        for path in files:
            if path.resolve() == THIS_MODULE or path.suffix in {".png", ".ttf", ".otf", ".jpg", ".gif", ".webp", ".ico", ".jsonl"}:
                continue
            checked, found = broken_section_pointers(path)
            total += checked
            problems.extend(found)
        assert total, "no `docs/x.md § name` pointers found: SECTION_RE no longer matches the code"
        assert not problems, "stale section pointers:\n  " + "\n  ".join(problems)
