"""The ``pinball`` theme: an early-80s pinball backbox, the quote on its
sixteen-segment display in RetroChunki.

Design notes: docs/themes.md § pinball
"""

from __future__ import annotations

import functools
import math
import random
import unicodedata

from PIL import Image, ImageChops, ImageDraw

from .._paths import BANGERS_REGULAR, ORNAMENT_FONT_CANDIDATES, RETROCHUNKI_BOLD
from ..fonts import font_has_glyph, load_font, normalize_dashes
from ..furniture import _row_digest
from ..layout import strip_underscore_emphasis, tokenize_quote
from ..palette import SPECTRA6, SPECTRA6_PALETTE, gray_pixel_access, snap_image_to_palette
from ..spec import FrameSpec
from ..text import fit_text_to_width

_PINBALL_SEED = 0x50494E42                     # PINB
_PINBALL_BACKGLASS_H = 124                     # the painted art band above the display
_PINBALL_SUN = (400, 196)                      # the sunburst's centre, below the band
_PINBALL_RAYS = 28
_PINBALL_RAY_INKS = ("red", "yellow", "blue", "yellow")
_PINBALL_PANEL = (20, 130, 779, 467)           # the display's bezel, outer edge
_PINBALL_INSET = 14                            # bezel to the first cell
_PINBALL_SCORE_SIZES = (60, 24)                # the score row's cell size range, px
_PINBALL_SCORE_MAX_H = 116                     # most height the score row may take
_PINBALL_BODY_SIZES = (34, 16)                 # the quote rows' cell size range, px; the longest
                                               # baked quote (260 chars) fits at 18
_PINBALL_ROW_LEAD = 1.32                       # row pitch, as a multiple of the cell size
_PINBALL_DIVIDER_GAP = 12                      # score row to quote rows
_PINBALL_NO_PHRASE = "SPECIAL"                 # the score row when the phrase is not on the page
_PINBALL_SLEEP_TITLE = "GOOD NIGHT"
_PINBALL_SLEEP_SCORE = "GAME OVER"
_PINBALL_SLEEP_BODY = "INSERT COIN"
# Characters the face sets in its narrow punctuation column, after a cell.
_PINBALL_NARROW = frozenset("!',.:;’")
# What the face lacks, as the display would show it. ``?`` is drawn from
# segments (``_pinball_qhook``) and is not mapped here.
_PINBALL_MAP = {
    "“": "'", "”": "'", "‘": "'", '"': "'", "`": "'",
    "—": "-", "–": "-", "…": "...",
    "(": "-", ")": "-", "[": "-", "]": "-", "{": "-", "}": "-",
    "&": " AND ", "_": "",
}
# The ``?`` hook: the segments a sixteen-segment display lights for it, as
# centroids in the cell's ink box (two top half-bars, the upper right
# vertical, the right half of the middle bar, the lower centre vertical).
# Its dot is the ``.`` of the punctuation column.
_PINBALL_QHOOK = ((0.29, 0.06), (0.70, 0.06), (0.91, 0.27), (0.70, 0.49), (0.50, 0.71))
_PINBALL_STAR_COUNT = 9


@functools.lru_cache(maxsize=64)
def _pinball_cell(size: int):
    """Per-size cell geometry and masks: ``(font, letter_adv, punct_adv,
    ascent, letter_ghost, punct_ghost, qhook)``. The masks are L images
    anchored with the baseline ``ascent + 2`` px from their top and the cell
    2 px in from their left."""
    font = load_font([RETROCHUNKI_BOLD, *ORNAMENT_FONT_CANDIDATES], size=size)
    letter_adv = font.getlength("A")
    punct_adv = font.getlength(".")
    ascent, descent = font.getmetrics()
    box = (int(math.ceil(letter_adv)) + 4, ascent + descent + 4)

    def mask(ch: str, *, ghost: bool) -> Image.Image:
        m = Image.new("L", box, 0)
        d = ImageDraw.Draw(m)
        d.text((2, ascent + 2), ch, font=font, fill=255, anchor="ls")
        if ghost:
            d.text((2, ascent + 2), ch, font=font, fill=255, anchor="ls", features=["ss01"])
        return m

    full = mask("A", ghost=True)
    return (font, letter_adv, punct_adv, ascent, _pinball_stipple(full), _pinball_stipple(mask(".", ghost=True)),
            _pinball_segments(full, _PINBALL_QHOOK))


def _pinball_stipple(mask: Image.Image) -> Image.Image:
    """``mask`` on a 1:1 checkerboard: the ghost segments are red / black
    half and half, faint on the panel and in an RGB preview alike."""
    w, h = mask.size
    checker = Image.new("L", (w, h), 0)
    px = gray_pixel_access(checker)
    for y in range(h):
        for x in range(w):
            if (x + y) & 1 == 0:
                px[x, y] = 255
    return ImageChops.multiply(mask.point(lambda v: 255 if v > 110 else 0), checker)


def _pinball_segments(full: Image.Image, wanted) -> Image.Image:
    """The union of the segments of the all-segments mask ``full`` whose
    centroids, in its ink box, sit nearest each of ``wanted``."""
    w, h = full.size
    px = gray_pixel_access(full)
    seen: set[tuple[int, int]] = set()
    comps: list[list[tuple[int, int]]] = []
    for y in range(h):
        for x in range(w):
            if px[x, y] > 127 and (x, y) not in seen:
                stack, pts = [(x, y)], []
                seen.add((x, y))
                while stack:
                    a, b = stack.pop()
                    pts.append((a, b))
                    for q in ((a + 1, b), (a - 1, b), (a, b + 1), (a, b - 1)):
                        if 0 <= q[0] < w and 0 <= q[1] < h and q not in seen and px[q] > 127:
                            seen.add(q)
                            stack.append(q)
                comps.append(pts)
    out = Image.new("L", (w, h), 0)
    bbox = full.getbbox()
    if not comps or bbox is None:
        return out
    bw, bh = max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])
    centres = [((sum(p[0] for p in c) / len(c) - bbox[0]) / bw, (sum(p[1] for p in c) / len(c) - bbox[1]) / bh)
               for c in comps]
    opx = gray_pixel_access(out)
    for tx, ty in wanted:
        k = min(range(len(comps)), key=lambda i: (centres[i][0] - tx) ** 2 + (centres[i][1] - ty) ** 2)
        for p in comps[k]:
            opx[p] = 255
    return out


def _pinball_text(text: str) -> str:
    """``text`` as the display can show it: capitals, accents folded, the
    face's missing marks mapped, anything else blanked. ``?`` is kept."""
    out: list[str] = []
    for ch in normalize_dashes(text):
        ch = _PINBALL_MAP.get(ch, ch)
        folded = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c)).upper()
        out.extend(c if c in " ?" or _pinball_has(c) else " " for c in folded)
    return "".join(out)


@functools.lru_cache(maxsize=256)
def _pinball_has(ch: str) -> bool:
    return ch.isprintable() and font_has_glyph(_pinball_cell(_PINBALL_BODY_SIZES[0])[0], ch)


def _pinball_units(segments) -> list[list]:
    """Display cells: ``[letter, letter_lit_phrase, punct, punct_lit_phrase]``.
    A narrow mark rides the punctuation column of the cell before it, as on
    the hardware; one with no letter before it takes a blank cell. ``?`` is
    its hook plus a ``.`` in the column. Runs of spaces collapse."""
    units: list[list] = []
    for chunk, bold in segments:
        for ch in _pinball_text(chunk):
            if ch == " ":
                if not units or (units[-1][0] == " " and not units[-1][2]):
                    continue
                units.append([" ", bold, "", bold])
            elif ch in _PINBALL_NARROW:
                if units and not units[-1][2] and units[-1][0] != " ":
                    units[-1][2], units[-1][3] = ch, bold
                else:
                    units.append([" ", bold, ch, bold])
            elif ch == "?":
                units.append(["?", bold, ".", bold])
            else:
                units.append([ch, bold, "", bold])
    while units and units[-1][0] == " " and not units[-1][2]:
        units.pop()
    return units


def _pinball_wrap(units: list[list], cols: int) -> list[list[list]]:
    """Greedy word wrap of display cells into rows of at most ``cols``; a
    word longer than a row is broken."""
    words: list[list[list]] = []
    cur: list[list] = []
    for u in units:
        if u[0] == " " and not u[2]:
            if cur:
                words.append(cur)
            cur = []
        else:
            cur.append(u)
    if cur:
        words.append(cur)
    rows: list[list[list]] = []
    row: list[list] = []
    for word in words:
        while len(word) > cols:
            if row:
                rows.append(row)
                row = []
            rows.append(word[:cols])
            word = word[cols:]
        if row and len(row) + 1 + len(word) > cols:
            rows.append(row)
            row = []
        if row:
            row.append([" ", False, "", False])
        row.extend(word)
    if row:
        rows.append(row)
    return rows


def _pinball_pitch(size: int) -> float:
    _font, letter_adv, punct_adv, *_ = _pinball_cell(size)
    return letter_adv + punct_adv


def _pinball_fit(units, width: float, height: float, sizes: tuple[int, int], max_rows: int | None = None):
    """The largest cell size, stepping by 2 px, at which ``units`` wrap into
    ``height``: ``(size, cols, rows)``. At the smallest size the rows are cut
    to what fits, the last one ending in an ellipsis."""
    hi, lo = sizes
    for size in range(hi, lo - 1, -2):
        cols = max(1, int(width // _pinball_pitch(size)))
        rows = _pinball_wrap(units, cols)
        fits = len(rows) * size * _PINBALL_ROW_LEAD <= height
        if fits and (max_rows is None or len(rows) <= max_rows):
            return size, cols, rows
    size = lo
    cols = max(1, int(width // _pinball_pitch(size)))
    rows = _pinball_wrap(units, cols)
    keep = max(1, min(max_rows or len(rows), int(height // (size * _PINBALL_ROW_LEAD))))
    if len(rows) > keep:
        # An ellipsis in three punctuation columns: the last kept cell's and
        # two blank cells'.
        rows = rows[:keep]
        last = rows[-1][: max(1, cols - 2)]
        last[-1] = [last[-1][0], last[-1][1], ".", last[-1][1]]
        rows[-1] = last + [[" ", False, ".", False], [" ", False, ".", False]]
    return size, cols, rows


def _pinball_paint_cells(image: Image.Image, rows, size: int, cols: int, x0: float, top: float,
                         n_rows: int, *, lit: str, phrase: str, align_rows: bool = True) -> None:
    """A grid of ``n_rows`` x ``cols`` cells from ``(x0, top)``, every cell's
    unlit segments ghosted, ``rows`` lit in it centred row by row and
    vertically. Cells in the matched phrase light in ``phrase``."""
    font, letter_adv, punct_adv, ascent, letter_ghost, punct_ghost, qhook = _pinball_cell(size)
    pitch = letter_adv + punct_adv
    lead = size * _PINBALL_ROW_LEAD
    draw = ImageDraw.Draw(image)
    ghost = SPECTRA6["red"]
    for r in range(n_rows):
        baseline = top + r * lead + ascent
        for c in range(cols):
            x = x0 + c * pitch
            image.paste(ghost, (int(round(x)) - 2, int(round(baseline)) - ascent - 2), letter_ghost)
            image.paste(ghost, (int(round(x + letter_adv)) - 2, int(round(baseline)) - ascent - 2), punct_ghost)
    first = (n_rows - len(rows)) // 2 if align_rows else 0
    for r, row in enumerate(rows):
        baseline = top + (first + r) * lead + ascent
        start = (cols - len(row)) // 2
        for c, (letter, lb, punct, pb) in enumerate(row):
            x = x0 + (start + c) * pitch
            if letter == "?":
                image.paste(SPECTRA6[phrase if lb else lit], (int(round(x)) - 2, int(round(baseline)) - ascent - 2), qhook)
            elif letter != " ":
                draw.text((x, baseline), letter, font=font, fill=SPECTRA6[phrase if lb else lit], anchor="ls")
            if punct:
                draw.text((x + letter_adv, baseline), punct, font=font, fill=SPECTRA6[phrase if pb else lit], anchor="ls")


def _pinball_paint_backglass(image: Image.Image, seed: int) -> None:
    """The painted art: a sunburst of red, yellow and blue rays rising from
    behind the display, and white four-point stars."""
    draw = ImageDraw.Draw(image)
    cx, cy = _PINBALL_SUN
    reach = 900
    step = 180 / _PINBALL_RAYS
    for k in range(_PINBALL_RAYS):
        a0, a1 = math.radians(180 + k * step), math.radians(180 + (k + 0.5) * step)
        ink = SPECTRA6[_PINBALL_RAY_INKS[k % len(_PINBALL_RAY_INKS)]]
        draw.polygon([(cx, cy), (cx + reach * math.cos(a0), cy + reach * math.sin(a0)),
                      (cx + reach * math.cos(a1), cy + reach * math.sin(a1))], fill=ink)
    # The rays fade into the black of the box toward the centre.
    draw.ellipse((cx - 150, cy - 150, cx + 150, cy + 150), fill=SPECTRA6["black"])
    rng = random.Random(seed)
    for _ in range(_PINBALL_STAR_COUNT):
        sx, sy, r = rng.randint(30, 770), rng.randint(10, _PINBALL_BACKGLASS_H - 12), rng.randint(4, 8)
        draw.polygon([(sx, sy - r), (sx + r // 3, sy), (sx, sy + r), (sx - r // 3, sy)], fill=SPECTRA6["white"])
        draw.polygon([(sx - r, sy), (sx, sy - r // 3), (sx + r, sy), (sx, sy + r // 3)], fill=SPECTRA6["white"])


def _pinball_paint_logo(draw: ImageDraw.ImageDraw, title: str, author: str) -> None:
    """The machine's name, the book's title, in Bangers: yellow, outlined red
    then black, the way a backglass logo is painted; the author beneath."""
    main = title.split(":")[0].split(";")[0].strip()
    if main and draw.textlength(title.upper(), font=load_font([BANGERS_REGULAR, *ORNAMENT_FONT_CANDIDATES], 40)) > 700:
        title = main
    font, text = fit_text_to_width(draw, title.upper(), [BANGERS_REGULAR, *ORNAMENT_FONT_CANDIDATES], 58, 700, floor=30)
    y = 50 if author else 62
    draw.text((400, y), text, font=font, fill=SPECTRA6["black"], anchor="mm", stroke_width=8, stroke_fill=SPECTRA6["black"])
    draw.text((400, y), text, font=font, fill=SPECTRA6["yellow"], anchor="mm", stroke_width=3, stroke_fill=SPECTRA6["red"])
    if author:
        small, who = fit_text_to_width(draw, author.upper(), [BANGERS_REGULAR, *ORNAMENT_FONT_CANDIDATES], 24, 560, floor=16)
        draw.text((400, 101), who, font=small, fill=SPECTRA6["white"], anchor="mm", stroke_width=4,
                  stroke_fill=SPECTRA6["black"])


def _pinball_paint_bezel(draw: ImageDraw.ImageDraw) -> None:
    """The display window: black glass in a blue bezel with a white bevel."""
    x0, y0, x1, y1 = _PINBALL_PANEL
    draw.rounded_rectangle((x0, y0, x1, y1), radius=12, fill=SPECTRA6["black"], outline=SPECTRA6["blue"], width=5)
    draw.rounded_rectangle((x0 + 6, y0 + 6, x1 - 6, y1 - 6), radius=8, outline=SPECTRA6["white"], width=1)


def _pinball_paint_display(image: Image.Image, score_units, body_units) -> None:
    """The score row (the phrase, big) over a blue rule, and the quote rows
    under it, every cell of both grids ghosted."""
    x0, y0, x1, y1 = _PINBALL_PANEL
    left, right = x0 + _PINBALL_INSET, x1 - _PINBALL_INSET
    width = right - left
    top = y0 + _PINBALL_INSET
    size, cols, rows = _pinball_fit(score_units, width, _PINBALL_SCORE_MAX_H, _PINBALL_SCORE_SIZES, max_rows=2)
    grid_w = cols * _pinball_pitch(size)
    _pinball_paint_cells(image, rows, size, cols, left + (width - grid_w) / 2, top, len(rows),
                         lit="white", phrase="white")
    # The rule sits just under the last score row's ink, not a full lead below.
    ascent = _pinball_cell(size)[3]
    divider = top + (len(rows) - 1) * size * _PINBALL_ROW_LEAD + ascent + _PINBALL_DIVIDER_GAP
    ImageDraw.Draw(image).line((left, divider, right, divider), fill=SPECTRA6["blue"], width=2)
    body_top = divider + _PINBALL_DIVIDER_GAP
    body_h = y1 - _PINBALL_INSET - body_top
    bsize, bcols, brows = _pinball_fit(body_units, width, body_h, (min(_PINBALL_BODY_SIZES[0], size - 6),
                                                                    _PINBALL_BODY_SIZES[1]))
    n_rows = max(len(brows), int(body_h // (bsize * _PINBALL_ROW_LEAD)))
    grid_w = bcols * _pinball_pitch(bsize)
    grid_h = n_rows * bsize * _PINBALL_ROW_LEAD
    _pinball_paint_cells(image, brows, bsize, bcols, left + (width - grid_w) / 2, body_top + (body_h - grid_h) / 2,
                         n_rows, lit="yellow", phrase="white")


def _pinball_finish(image: Image.Image, width: int, height: int) -> Image.Image:
    image = snap_image_to_palette(image, SPECTRA6_PALETTE)
    if (width, height) != (800, 480):
        image = image.resize((width, height), Image.Resampling.NEAREST)
    return image


def _pinball_phrase(segments) -> str:
    phrase = " ".join("".join(chunk for chunk, bold in segments if bold).split())
    return phrase.rstrip('”"\'’.,;:!?').strip()


def render_pinball_frame(time_str: str, quote_row: dict, width: int, height: int) -> Image.Image:
    """A pinball backbox: the book as the machine, the phrase on the score
    display, the quote on the rows under it (see docs/themes.md)."""
    del time_str
    image = Image.new("RGB", (800, 480), SPECTRA6["black"])
    _pinball_paint_backglass(image, _row_digest(quote_row) ^ _PINBALL_SEED)
    draw = ImageDraw.Draw(image)
    title = (quote_row.get("title") or "").strip() or "Idle Play"
    _pinball_paint_logo(draw, title, (quote_row.get("author") or "").strip())
    _pinball_paint_bezel(draw)
    text = strip_underscore_emphasis(quote_row.get("display_quote") or "").strip()
    segments = [s for s in tokenize_quote(text, quote_row.get("matched_text") or "") if s[0]]
    phrase = _pinball_phrase(segments) or _PINBALL_NO_PHRASE
    _pinball_paint_display(image, _pinball_units([(phrase, True)]), _pinball_units(segments))
    return _pinball_finish(image, width, height)


def render_pinball_sleep(time_str: str, width: int, height: int) -> Image.Image:
    """The quiet-hours frame: the machine in attract mode with nobody
    playing: GAME OVER on the score row, INSERT COIN on the dark grid under
    it. ``time_str`` is unused."""
    del time_str
    image = Image.new("RGB", (800, 480), SPECTRA6["black"])
    _pinball_paint_backglass(image, _PINBALL_SEED)
    draw = ImageDraw.Draw(image)
    _pinball_paint_logo(draw, _PINBALL_SLEEP_TITLE, "")
    _pinball_paint_bezel(draw)
    _pinball_paint_display(image, _pinball_units([(_PINBALL_SLEEP_SCORE, True)]),
                           _pinball_units([(_PINBALL_SLEEP_BODY, False)]))
    return _pinball_finish(image, width, height)


SPEC = FrameSpec(themes=("pinball",), render=render_pinball_frame, sleep=render_pinball_sleep)
