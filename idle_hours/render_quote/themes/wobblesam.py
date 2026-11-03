"""The ``wobblesam`` theme: an optician's eye chart set in Wobblesam, the face
whose letters have eyes.

Design notes: docs/themes.md § wobblesam
"""

from __future__ import annotations

from typing import Any

from PIL import Image, ImageDraw

from .._paths import ORNAMENT_FONT_CANDIDATES, WOBBLESAM_BOLD, WOBBLESAM_REGULAR
from ..fonts import _font_ascent, load_font, normalize_dashes
from ..furniture import _paint_placed, _place_quote
from ..layout import strip_underscore_emphasis, tokenize_quote
from ..palette import SPECTRA6, SPECTRA6_PALETTE, snap_image_to_palette
from ..spec import FrameSpec
from ..text import fit_text_to_width

_WOBBLESAM_CARD = (8, 8, 791, 471)            # the printed card's black edge
_WOBBLESAM_ROWS_X = (104, 724)                # the chart's letter column
_WOBBLESAM_LABEL_X = 26                       # acuity fractions, flush left
_WOBBLESAM_NUMBER_X = 770                     # line numbers, flush right
_WOBBLESAM_TOP = 26                           # top of the top line's ink box
_WOBBLESAM_BOTTOM = 432                       # rows end here; the byline sits below
_WOBBLESAM_BYLINE_Y = 456                     # byline baseline
_WOBBLESAM_TOP_MAX = 104                      # the top line's size range
_WOBBLESAM_TOP_MIN = 40
_WOBBLESAM_ROW_RATIO = 0.84                   # each row this much smaller than the last
_WOBBLESAM_ROW_FLOOR = 18                     # no row is set smaller
_WOBBLESAM_ROW_LEAD = 1.22                    # row pitch, as a multiple of its size
_WOBBLESAM_LABEL_SIZE = 15
_WOBBLESAM_BAR_GAP = 8                        # extra space under a line that carries a bar
_WOBBLESAM_MAX_SPREAD = 16                    # most leftover height added to one row gap
# The printed Snellen fractions, top line first; a line past the last has a
# number and no fraction.
_WOBBLESAM_ACUITY = ("20/200", "20/100", "20/70", "20/50", "20/40", "20/30", "20/25", "20/20", "20/15", "20/13", "20/10")
# The two bars a chart prints under a line: green under 20/40, red under 20/20.
_WOBBLESAM_BARS = {"20/40": "green", "20/20": "red"}
_WOBBLESAM_TRAILING = '”"\'’.,;:!?'
_WOBBLESAM_FALLBACK_TOP = "E"                 # the top line when no phrase is on the page
_WOBBLESAM_SLEEP_ROWS = ("Z", "Z Z", "z z z", "z z z z", "z z z z z", "z z z z z z")


def _wobblesam_font(size: int, *, bold: bool = False):
    return load_font([WOBBLESAM_BOLD if bold else WOBBLESAM_REGULAR, *ORNAMENT_FONT_CANDIDATES], size=size)


def _wobblesam_quote(quote_row: dict) -> tuple[list[tuple[str, bool]], str]:
    """The quote as ``tokenize_quote`` segments, and the phrase as it reads in
    the quote (empty when it is not there)."""
    text = normalize_dashes(strip_underscore_emphasis(quote_row.get("display_quote") or "")).strip()
    segments = [s for s in tokenize_quote(text, quote_row.get("matched_text") or "") if s[0]]
    phrase = " ".join("".join(chunk for chunk, bold in segments if bold).split())
    # ``tokenize_quote`` carries trailing punctuation into the phrase; the top
    # line is the phrase alone.
    return segments, phrase.rstrip(_WOBBLESAM_TRAILING).strip()


def _wobblesam_words(segments: list[tuple[str, bool]]) -> list[list[tuple[str, bool]]]:
    """Whole words, each a list of styled pieces. A word is glued across a
    segment seam (``"seven)"`` is one word, ``seven`` bold), so a row only
    ever breaks at whitespace: ``wrap_styled_text``'s rule."""
    words: list[list[tuple[str, bool]]] = []
    open_word = False
    for chunk, bold in segments:
        for i, piece in enumerate(chunk.split(" ")):
            if i:
                open_word = False
            if not piece:
                continue
            if open_word:
                words[-1].append((piece, bold))
            else:
                words.append([(piece, bold)])
                open_word = True
    return words


def _wobblesam_row_fonts(size: int):
    return _wobblesam_font(size), _wobblesam_font(size, bold=True)


def _wobblesam_word_width(draw, word, size: int) -> float:
    regular, bold = _wobblesam_row_fonts(size)
    return sum(draw.textlength(piece, font=bold if b else regular) for piece, b in word)


def _wobblesam_pitch(size: int, index: int) -> float:
    """Height a row of ``size`` px takes as chart line ``index``."""
    return size * _WOBBLESAM_ROW_LEAD + (_WOBBLESAM_BAR_GAP if _wobblesam_bar(index) else 0)


def _wobblesam_descend(draw, words, first: int, height: int, first_index: int):
    """Set ``words`` in rows that shrink by ``_WOBBLESAM_ROW_RATIO`` from
    ``first`` px down to the floor, the first of them chart line
    ``first_index``. Returns ``[(size, [word, …]), …]``, or ``None`` when the
    rows overrun ``height``."""
    width = _WOBBLESAM_ROWS_X[1] - _WOBBLESAM_ROWS_X[0]
    rows: list[tuple[int, list]] = []
    used, i, n = 0.0, 0, 0
    while i < len(words):
        size = max(_WOBBLESAM_ROW_FLOOR, round(first * _WOBBLESAM_ROW_RATIO ** n))
        space = draw.textlength(" ", font=_wobblesam_font(size))
        row, line_w = [words[i]], _wobblesam_word_width(draw, words[i], size)
        i += 1
        while i < len(words):
            w = _wobblesam_word_width(draw, words[i], size)
            if line_w + space + w > width:
                break
            row.append(words[i])
            line_w += space + w
            i += 1
        used += _wobblesam_pitch(size, first_index + n)
        if used > height:
            return None
        rows.append((size, row))
        n += 1
    return rows


def _wobblesam_top_line(draw, phrase: str) -> tuple[Any, list[str]]:
    """The top line, the chart's big "E": the time phrase at the largest size
    that fits on one line, or balanced over two, ellipsised only past that."""
    width = _WOBBLESAM_ROWS_X[1] - _WOBBLESAM_ROWS_X[0]
    text = phrase or _WOBBLESAM_FALLBACK_TOP
    for size in range(_WOBBLESAM_TOP_MAX, _WOBBLESAM_TOP_MIN - 1, -4):
        font = _wobblesam_font(size, bold=True)
        if draw.textlength(text, font=font) <= width:
            return font, [text]
    words = text.split()
    if len(words) > 1:
        cut = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(" ".join(words[k:]))))
        halves = [" ".join(words[:cut]), " ".join(words[cut:])]
        for size in range(_WOBBLESAM_TOP_MIN + 8, 31, -4):
            font = _wobblesam_font(size, bold=True)
            if all(draw.textlength(h, font=font) <= width for h in halves):
                return font, halves
    font, fitted = fit_text_to_width(draw, text, [WOBBLESAM_BOLD, *ORNAMENT_FONT_CANDIDATES], _WOBBLESAM_TOP_MIN, width,
                                     floor=_WOBBLESAM_TOP_MIN)
    return font, [fitted]


def _wobblesam_paint_card(draw: ImageDraw.ImageDraw) -> None:
    """The printed card: a black edge with rounded corners and a hairline
    inside it."""
    x0, y0, x1, y1 = _WOBBLESAM_CARD
    draw.rounded_rectangle((x0, y0, x1, y1), radius=14, outline=SPECTRA6["black"], width=3)
    draw.rounded_rectangle((x0 + 7, y0 + 7, x1 - 7, y1 - 7), radius=9, outline=SPECTRA6["black"], width=1)


def _wobblesam_label(index: int) -> str:
    return _WOBBLESAM_ACUITY[index] if index < len(_WOBBLESAM_ACUITY) else ""


def _wobblesam_bar(index: int) -> str | None:
    """The ink of the bar under line ``index``, if it carries one."""
    return _WOBBLESAM_BARS.get(_wobblesam_label(index))


def _wobblesam_paint_margin(draw: ImageDraw.ImageDraw, index: int, baseline: int, mid: int) -> None:
    """A line's acuity fraction on the left, its number on the right, and the
    chart's green / red bar under the 20/40 and 20/20 lines."""
    font = _wobblesam_font(_WOBBLESAM_LABEL_SIZE)
    label = _wobblesam_label(index)
    if label:
        draw.text((_WOBBLESAM_LABEL_X, mid), label, font=font, fill=SPECTRA6["black"], anchor="lm")
    draw.text((_WOBBLESAM_NUMBER_X, mid), str(index + 1), font=font, fill=SPECTRA6["black"], anchor="rm")
    bar = _wobblesam_bar(index)
    if bar:
        draw.rectangle((_WOBBLESAM_LABEL_X, baseline + 6, _WOBBLESAM_NUMBER_X, baseline + 8), fill=SPECTRA6[bar])


def _wobblesam_top_height(font, lines: list[str]) -> int:
    ascent, descent = font.getmetrics()
    return len(lines) * (ascent + descent + 8)


def _wobblesam_paint_top(draw: ImageDraw.ImageDraw, font, lines: list[str], top: int) -> None:
    """The top line(s), centred and solid black, ``_wobblesam_top_height`` tall."""
    cx = sum(_WOBBLESAM_ROWS_X) // 2
    ascent, descent = font.getmetrics()
    y = top
    for k, text in enumerate(lines):
        baseline = y + ascent
        draw.text((cx, baseline), text, font=font, fill=SPECTRA6["black"], anchor="ms")
        _wobblesam_paint_margin(draw, k, baseline, baseline - ascent // 3)
        y = baseline + descent + 8


def _wobblesam_rows_spread(rows, first_index: int, height: float) -> tuple[float, float]:
    """``(spread, total)``: the extra gap per row that shares out the height
    left in ``height`` (capped, so a short chart does not float apart), and
    the rows' total height with it."""
    used = sum(_wobblesam_pitch(size, first_index + n) for n, (size, _w) in enumerate(rows))
    spread = min(_WOBBLESAM_MAX_SPREAD, max(0.0, (height - used) / max(1, len(rows))))
    return spread, used + spread * len(rows)


def _wobblesam_paint_rows(draw: ImageDraw.ImageDraw, rows, top: float, first_index: int, spread: float) -> None:
    """The descending rows, centred, the phrase's own words in Bold, each gap
    widened by ``spread``."""
    cx = sum(_WOBBLESAM_ROWS_X) // 2
    y = float(top) + spread / 2
    for n, (size, words) in enumerate(rows):
        regular, bold = _wobblesam_row_fonts(size)
        space = draw.textlength(" ", font=regular)
        line_w = sum(_wobblesam_word_width(draw, w, size) for w in words) + space * (len(words) - 1)
        baseline = int(y + _font_ascent(regular))
        x = cx - line_w / 2
        for word in words:
            for piece, b in word:
                draw.text((x, baseline), piece, font=bold if b else regular, fill=SPECTRA6["black"], anchor="ls")
                x += draw.textlength(piece, font=bold if b else regular)
            x += space
        _wobblesam_paint_margin(draw, first_index + n, baseline, baseline - _font_ascent(regular) // 3)
        y += _wobblesam_pitch(size, first_index + n) + spread


def _wobblesam_paint_byline(draw: ImageDraw.ImageDraw, quote_row: dict) -> None:
    """Author and title, small and centred under the chart."""
    text = ", ".join(p for p in ((quote_row.get("author") or "").strip(), (quote_row.get("title") or "").strip()) if p)
    if not text:
        return
    width = _WOBBLESAM_ROWS_X[1] - _WOBBLESAM_ROWS_X[0]
    font, text = fit_text_to_width(draw, text, [WOBBLESAM_REGULAR, *ORNAMENT_FONT_CANDIDATES], 20, width, floor=14)
    draw.text((sum(_WOBBLESAM_ROWS_X) // 2, _WOBBLESAM_BYLINE_Y), text, font=font, fill=SPECTRA6["black"], anchor="ms")


def _wobblesam_finish(image: Image.Image, width: int, height: int) -> Image.Image:
    image = snap_image_to_palette(image, SPECTRA6_PALETTE)
    if (width, height) != (800, 480):
        image = image.resize((width, height), Image.Resampling.NEAREST)
    return image


def render_wobblesam_frame(time_str: str, quote_row: dict, width: int, height: int) -> Image.Image:
    """An eye chart: the time phrase as the big top line, the quote in rows
    that shrink beneath it (see docs/themes.md)."""
    del time_str
    image = Image.new("RGB", (800, 480), SPECTRA6["white"])
    draw = ImageDraw.Draw(image)
    _wobblesam_paint_card(draw)
    segments, phrase = _wobblesam_quote(quote_row)
    top_font, top_lines = _wobblesam_top_line(draw, phrase)
    top_h = _wobblesam_top_height(top_font, top_lines) + 6
    height_left = _WOBBLESAM_BOTTOM - _WOBBLESAM_TOP - top_h
    words = _wobblesam_words(segments)
    rows = None
    # The biggest second line that lets the whole quote fit, one step down
    # from the top line it hangs under.
    for first in range(int(top_font.size * _WOBBLESAM_ROW_RATIO), _WOBBLESAM_ROW_FLOOR - 1, -2):
        rows = _wobblesam_descend(draw, words, first, height_left, len(top_lines))
        if rows is not None:
            break
    if rows is not None:
        spread, rows_h = _wobblesam_rows_spread(rows, len(top_lines), height_left)
        # A chart shorter than the card sits in its middle.
        offset = max(0, int(height_left - rows_h) // 2)
        _wobblesam_paint_top(draw, top_font, top_lines, _WOBBLESAM_TOP + offset)
        rows_top = _WOBBLESAM_TOP + offset + top_h
        _wobblesam_paint_rows(draw, rows, rows_top, len(top_lines), spread)
    else:
        _wobblesam_paint_top(draw, top_font, top_lines, _WOBBLESAM_TOP)
        rows_top = _WOBBLESAM_TOP + top_h
        # Too long to descend: set it level, fitted and truncated by the
        # shared layout, under a chart that still has its top line.
        placed = _place_quote(draw, quote_row, (_WOBBLESAM_ROWS_X[0], rows_top, _WOBBLESAM_ROWS_X[1], _WOBBLESAM_BOTTOM),
                              theme="wobblesam", font_max=_WOBBLESAM_ROW_FLOOR, font_min=12, line_height_mult=1.2)
        _paint_placed(draw, placed, SPECTRA6["black"], SPECTRA6["black"])
    _wobblesam_paint_byline(draw, quote_row)
    return _wobblesam_finish(image, width, height)


def render_wobblesam_sleep(time_str: str, width: int, height: int) -> Image.Image:
    """The quiet-hours frame: the chart read in z's, a big "Z" on top and a
    longer, smaller row of z's on every line down. ``time_str`` is unused."""
    del time_str
    image = Image.new("RGB", (800, 480), SPECTRA6["white"])
    draw = ImageDraw.Draw(image)
    _wobblesam_paint_card(draw)
    top_font, top_lines = _wobblesam_font(_WOBBLESAM_TOP_MAX, bold=True), [_WOBBLESAM_SLEEP_ROWS[0]]
    _wobblesam_paint_top(draw, top_font, top_lines, _WOBBLESAM_TOP)
    y = _WOBBLESAM_TOP + _wobblesam_top_height(top_font, top_lines) + 6
    first = int(_WOBBLESAM_TOP_MAX * _WOBBLESAM_ROW_RATIO * 0.8)
    rows = [(max(_WOBBLESAM_ROW_FLOOR, round(first * _WOBBLESAM_ROW_RATIO ** n)), [[(row, True)]])
            for n, row in enumerate(_WOBBLESAM_SLEEP_ROWS[1:])]
    spread, _h = _wobblesam_rows_spread(rows, 1, _WOBBLESAM_BOTTOM + 30 - y)
    _wobblesam_paint_rows(draw, rows, y, 1, spread)
    return _wobblesam_finish(image, width, height)


SPEC = FrameSpec(themes=("wobblesam",), render=render_wobblesam_frame, sleep=render_wobblesam_sleep)
