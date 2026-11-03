"""The ``wobblesam`` theme: a spiral notebook page in Wobblesam, whose margin
doodles all look at the time.

Design notes: docs/themes.md § wobblesam
"""

from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw

from .._paths import ORNAMENT_FONT_CANDIDATES, WOBBLESAM_BOLD, WOBBLESAM_REGULAR
from ..fonts import _font_ascent, load_font
from ..furniture import _place_quote, _row_digest
from ..palette import SPECTRA6, SPECTRA6_PALETTE, snap_image_to_palette
from ..spec import FrameSpec
from ..text import fit_text_to_width

_WOBBLESAM_SEED = 0x574F4242                 # WOBB
_WOBBLESAM_COIL_X = 20                       # centre of the binding's punched holes
_WOBBLESAM_COIL_PITCH = 24
_WOBBLESAM_MARGIN_X = 92                     # the red margin line
_WOBBLESAM_RULE_X0 = 34                      # rules start just right of the holes
_WOBBLESAM_RULE_TOP = 70                     # no rule above the header strip
_WOBBLESAM_RULE_BOTTOM = 470
_WOBBLESAM_BODY = (114, 84, 766, 380)
_WOBBLESAM_BYLINE_MIN_Y = 414                # lowest a byline baseline may sit is the canvas
_WOBBLESAM_BYLINE_MAX_W = 640
# Where a doodled eye may sit: (cx, cy, radius). The left column is the space
# between the binding and the margin line; the top row is the header strip
# above the first rule. Neither ever holds text.
_WOBBLESAM_LEFT_SLOTS = ((62, 104, 18), (60, 186, 15), (63, 262, 20), (60, 344, 16), (62, 424, 18))
_WOBBLESAM_TOP_SLOTS = ((168, 36, 20), (282, 34, 16), (402, 37, 21), (520, 34, 17), (640, 36, 20), (748, 35, 18))
_WOBBLESAM_EYES_PER_EDGE = 3
# Iris inks, ``None`` for a plain black pupil. Weighted toward plain.
_WOBBLESAM_IRISES = (None, None, "blue", "green")
_WOBBLESAM_SLEEP_TEXT = "Lights out."
_WOBBLESAM_SLEEP_Z = (("z", 26, 0), ("z", 34, 30), ("Z", 44, 66))   # (glyph, size, offset) off the full stop


def _wobblesam_font(size: int, *, bold: bool = False):
    return load_font([WOBBLESAM_BOLD if bold else WOBBLESAM_REGULAR, *ORNAMENT_FONT_CANDIDATES], size=size)


def _wobblesam_paint_binding(draw: ImageDraw.ImageDraw, height: int) -> None:
    """The spiral: a punched hole every 24 px, the wire running into it on a
    slant from over the page's left edge."""
    black = SPECTRA6["black"]
    x = _WOBBLESAM_COIL_X
    for y in range(_WOBBLESAM_COIL_PITCH // 2, height, _WOBBLESAM_COIL_PITCH):
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=black)
        draw.line((0, y - 9, x, y), fill=black, width=4)


def _wobblesam_paint_rules(draw: ImageDraw.ImageDraw, rules: list[int]) -> None:
    """Blue ruled lines at the writing's own pitch, and the red margin line."""
    for y in rules:
        draw.line((_WOBBLESAM_RULE_X0, y, 799, y), fill=SPECTRA6["blue"], width=1)
    x = _WOBBLESAM_MARGIN_X
    draw.line((x, 0, x, 479), fill=SPECTRA6["red"], width=2)


def _wobblesam_rules(placed: list, fallback_pitch: int = 38) -> tuple[list[int], int]:
    """The rule rows, run from the quote's baselines so the writing sits on
    them, and their pitch."""
    if placed:
        pitch = placed[0][6]
        anchor = placed[0][1] + _font_ascent(placed[0][3]) + 3
    else:
        pitch = fallback_pitch
        anchor = _WOBBLESAM_BODY[1] + pitch
    first = anchor - ((anchor - _WOBBLESAM_RULE_TOP) // pitch) * pitch
    return list(range(first, _WOBBLESAM_RULE_BOTTOM + 1, pitch)), pitch


def _wobblesam_paint_highlight(draw: ImageDraw.ImageDraw, placed: list, seed: int) -> None:
    """A yellow highlighter swipe over the matched phrase: a band from just
    under the cap height into the descenders, its long edges wavering and its
    ends cut on a slant, one stroke per line."""
    rng = random.Random(seed)
    yellow = SPECTRA6["yellow"]
    for x, y, chunk, font, is_bold, w, _lh in placed:
        if not is_bold or not chunk.strip():
            continue
        lead = len(chunk) - len(chunk.lstrip())
        trail = len(chunk) - len(chunk.rstrip())
        x0 = x + (draw.textlength(chunk[:lead], font=font) if lead else 0) - 5
        x1 = x + w - (draw.textlength(chunk[len(chunk) - trail:], font=font) if trail else 0) + 5
        ascent, descent = font.getmetrics()
        top, bottom = y + ascent * 0.32, y + ascent + descent * 0.55
        steps = max(2, int((x1 - x0) // 14))
        upper = [(x0 + (x1 - x0) * i / steps, top + rng.uniform(-1.5, 1.5)) for i in range(steps + 1)]
        lower = [(x0 + (x1 - x0) * i / steps, bottom + rng.uniform(-1.5, 1.5)) for i in range(steps, -1, -1)]
        slant = rng.uniform(3, 6)
        upper[0] = (upper[0][0] + slant, upper[0][1])
        lower[0] = (lower[0][0] + slant, lower[0][1])
        draw.polygon(upper + lower, fill=yellow)


def _wobblesam_target(placed: list) -> tuple[float, float]:
    """Where the eyes look: the centre of the matched phrase's ink, or of the
    body when the phrase is not on the page."""
    points = [(x + w / 2, y + _font_ascent(font) * 0.7) for x, y, chunk, font, is_bold, w, _lh in placed
              if is_bold and chunk.strip()]
    if not points:
        x0, y0, x1, y1 = _WOBBLESAM_BODY
        return (x0 + x1) / 2, (y0 + y1) / 2
    return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)


def _wobblesam_eyes(seed: int) -> list[tuple[int, int, int, str | None, bool]]:
    """Three eyes on each edge, drawn from the slots: ``(cx, cy, r, iris, lashes)``."""
    rng = random.Random(seed)
    eyes = []
    for slots in (_WOBBLESAM_LEFT_SLOTS, _WOBBLESAM_TOP_SLOTS):
        for cx, cy, r in sorted(rng.sample(slots, _WOBBLESAM_EYES_PER_EDGE)):
            eyes.append((cx, cy, r, rng.choice(_WOBBLESAM_IRISES), rng.random() < 0.5))
    return eyes


def _wobblesam_paint_eye(draw: ImageDraw.ImageDraw, eye, target: tuple[float, float] | None) -> None:
    """One marker eyeball looking at ``target``; shut, lashes down, with ``None``."""
    cx, cy, r, iris, lashes = eye
    black, white = SPECTRA6["black"], SPECTRA6["white"]
    if target is None:
        # Every shut eye gets lashes: a bare lid reads as a smile.
        draw.arc((cx - r, cy - r, cx + r, cy + r), start=15, end=165, fill=black, width=3)
        for deg in (55, 90, 125):
            a = math.radians(deg)
            sx, sy = cx + r * math.cos(a), cy + r * math.sin(a)
            draw.line((sx, sy, sx + r * 0.45 * math.cos(a), sy + r * 0.45 * math.sin(a)), fill=black, width=3)
        return
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=white, outline=black, width=3)
    if lashes:
        for deg in (-125, -90, -55):
            a = math.radians(deg)
            sx, sy = cx + r * math.cos(a), cy + r * math.sin(a)
            draw.line((sx, sy, sx + r * 0.45 * math.cos(a), sy + r * 0.45 * math.sin(a)), fill=black, width=3)
    pupil = r * (0.34 if iris else 0.44)
    extent = r * 0.6 if iris else pupil
    dx, dy = target[0] - cx, target[1] - cy
    dist = math.hypot(dx, dy) or 1.0
    reach = max(0.0, r - 3 - extent)
    px, py = cx + dx / dist * reach, cy + dy / dist * reach
    if iris:
        draw.ellipse((px - extent, py - extent, px + extent, py + extent), fill=SPECTRA6[iris])
    draw.ellipse((px - pupil, py - pupil, px + pupil, py + pupil), fill=black)
    glint = max(1.5, r * 0.12)
    gx, gy = px - pupil * 0.4, py - pupil * 0.4
    draw.ellipse((gx - glint, gy - glint, gx + glint, gy + glint), fill=white)


def _wobblesam_paint_eyes(draw: ImageDraw.ImageDraw, eyes, target: tuple[float, float] | None) -> None:
    for eye in eyes:
        _wobblesam_paint_eye(draw, eye, target)


def _wobblesam_paint_byline(draw: ImageDraw.ImageDraw, quote_row: dict, rules: list[int], last_rule: int) -> None:
    """Author and title in ballpoint blue, on the first free rule under the quote.

    No ``fallback_title``: its ``#`` is one of the ASCII marks the face lacks,
    and it is built here, after ``render``'s glyph fallbacks have run."""
    author = (quote_row.get("author") or "").strip()
    title = (quote_row.get("title") or "").strip()
    text = ", ".join(p for p in (author, title) if p)
    if not text:
        return
    floor = max(_WOBBLESAM_BYLINE_MIN_Y, last_rule + 1)
    free = [y for y in rules if y >= floor]
    baseline = free[0] if free else _WOBBLESAM_RULE_BOTTOM
    font, text = fit_text_to_width(draw, "— " + text, [WOBBLESAM_REGULAR, *ORNAMENT_FONT_CANDIDATES], 26,
                                   _WOBBLESAM_BYLINE_MAX_W, floor=18)
    draw.text((_WOBBLESAM_BODY[0], baseline - 3), text, font=font, fill=SPECTRA6["blue"], anchor="ls")


def _wobblesam_finish(image: Image.Image, width: int, height: int) -> Image.Image:
    image = snap_image_to_palette(image, SPECTRA6_PALETTE)
    if (width, height) != (800, 480):
        image = image.resize((width, height), Image.Resampling.NEAREST)
    return image


def render_wobblesam_frame(time_str: str, quote_row: dict, width: int, height: int) -> Image.Image:
    """A spiral notebook page whose margin eyes look at the time (see docs/themes.md)."""
    del time_str
    image = Image.new("RGB", (800, 480), SPECTRA6["white"])
    draw = ImageDraw.Draw(image)
    seed = _row_digest(quote_row) ^ _WOBBLESAM_SEED
    placed = _place_quote(draw, quote_row, _WOBBLESAM_BODY, theme="wobblesam",
                          font_max=52, font_min=18, line_height_mult=1.32)
    if placed:
        # Centre the block on the page's rule grid: a short quote sits mid-page.
        x0, y0, x1, y1 = _WOBBLESAM_BODY
        pitch = placed[0][6]
        used = placed[-1][1] - placed[0][1] + pitch
        dy = max(0, (y1 - y0 - used) // 2)
        placed = [(x, y + dy, *rest) for x, y, *rest in placed]
    rules, _pitch = _wobblesam_rules(placed)
    _wobblesam_paint_highlight(draw, placed, seed)
    _wobblesam_paint_rules(draw, rules)
    _wobblesam_paint_binding(draw, 480)
    for x, y, chunk, font, _is_bold, *_ in placed:
        draw.text((x, y), chunk, font=font, fill=SPECTRA6["black"])
    last = placed[-1][1] + _font_ascent(placed[-1][3]) + 3 if placed else _WOBBLESAM_BODY[3]
    _wobblesam_paint_byline(draw, quote_row, rules, last)
    _wobblesam_paint_eyes(draw, _wobblesam_eyes(seed), _wobblesam_target(placed))
    return _wobblesam_finish(image, width, height)


def render_wobblesam_sleep(time_str: str, width: int, height: int) -> Image.Image:
    """The quiet-hours frame: the same page with every doodled eye shut,
    "Lights out." on the middle rule, and a stack of z's off one eye.
    ``time_str`` is unused: nothing on the frame tells the time."""
    del time_str
    image = Image.new("RGB", (800, 480), SPECTRA6["white"])
    draw = ImageDraw.Draw(image)
    font = _wobblesam_font(64, bold=True)
    x0, y0, x1, y1 = _WOBBLESAM_BODY
    tw = draw.textlength(_WOBBLESAM_SLEEP_TEXT, font=font)
    ascent = _font_ascent(font)
    top = (y0 + y1) // 2 - ascent // 2
    pitch = int(round(sum(font.getmetrics()) * 1.32))
    placed = [((x0 + x1 - tw) // 2, top, _WOBBLESAM_SLEEP_TEXT, font, False, int(tw), pitch)]
    rules, _pitch = _wobblesam_rules(placed)
    _wobblesam_paint_rules(draw, rules)
    _wobblesam_paint_binding(draw, 480)
    draw.text(placed[0][:2], _WOBBLESAM_SLEEP_TEXT, font=font, fill=SPECTRA6["black"])
    _wobblesam_paint_eyes(draw, _wobblesam_eyes(_WOBBLESAM_SEED), None)
    # z's drifting up and away from the full stop, in ballpoint blue.
    x, baseline = placed[0][0] + tw + 14, top + ascent
    for glyph, size, offset in _WOBBLESAM_SLEEP_Z:
        draw.text((x + offset, baseline - 18 - offset * 0.9), glyph, font=_wobblesam_font(size),
                  fill=SPECTRA6["blue"], anchor="ls")
    return _wobblesam_finish(image, width, height)


SPEC = FrameSpec(themes=("wobblesam",), render=render_wobblesam_frame, sleep=render_wobblesam_sleep)
