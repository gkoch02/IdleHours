"""What the ``seneschal`` and ``seneschal_light`` themes share: Seneschal's main screen, the quote the one thing on.

A frame is not told which theme it draws, so each look is a module of its own over this one.
Design notes: docs/themes.md § seneschal
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageDraw

from .._paths import META_FONT_BOLD_CANDIDATES, MICHROMA_REGULAR, SAIRA_VARIABLE
from ..fonts import load_font
from ..furniture import fallback_title
from ..palette import SPECTRA6, SPECTRA6_PALETTE, BAYER_8x8, gray_pixel_access, pixel_access, snap_image_to_palette
from ..primitives import _bayer_threshold_field, paint_neon_mask, wrap_quote_into_masks
from ..text import draw_text_dithered, draw_tracked, tracked_width

_SENESCHAL_LEFT, _SENESCHAL_RIGHT = 44, 756
_SENESCHAL_PANEL = (44, 140, 756, 370)
_SENESCHAL_PANEL_CUT = 14
_SENESCHAL_QUOTE_RECT = (104, 162, 726, 318)
_SENESCHAL_BYLINE_Y = 337
_SENESCHAL_CELL_TOP, _SENESCHAL_CELL_H, _SENESCHAL_CELL_GAP = 410, 42, 6
_SENESCHAL_SCENE: dict = {}
_SENESCHAL_SLEEP_ROW: dict[str, str] = {
    "display_quote": "Everything is off for the night. The lights come back on in the morning.",
    "matched_text": "for the night",
    "author": "Seneschal",
    "title": "All Off",
}


@dataclass(frozen=True)
class _SeneschalAccent:
    """One of the app's six lit colours as the panel can show it: a major
    ink, and a minor one stippled into it at ``share`` where the panel has
    no ink of its own (ember, teal, violet)."""

    name: str
    major: str
    minor: str | None = None
    share: float = 0.0


# The app's six, in its own order; the hour takes them round the face.
_SENESCHAL_ACCENTS = (
    _SeneschalAccent("gold", "yellow"),
    _SeneschalAccent("ember", "red", "yellow", 0.375),
    _SeneschalAccent("crimson", "red"),
    _SeneschalAccent("phosphor", "green"),
    _SeneschalAccent("teal", "green", "blue", 0.5),
    _SeneschalAccent("violet", "blue", "red", 0.4),
)


def _seneschal_accent(hour12: int) -> _SeneschalAccent:
    """Twelve and six gold, one and seven ember, and on round the face."""
    return _SENESCHAL_ACCENTS[hour12 % 6]


def _seneschal_ink(name: str | None):
    return SPECTRA6[name] if name else None


def _seneschal_wide(size: int):
    return load_font([MICHROMA_REGULAR, *META_FONT_BOLD_CANDIDATES], size=size)


def _seneschal_cond(size: int, weight: int = 600):
    """Saira condensed, the app's interface caps (width 72 on the axis)."""
    return load_font([(SAIRA_VARIABLE, (weight, 72)), *META_FONT_BOLD_CANDIDATES], size=size)


def _seneschal_bevelled(rect, cut: int) -> list[tuple[int, int]]:
    """A rect with its bottom-right corner cut at 45°, as the app's tiles are."""
    x0, y0, x1, y1 = rect
    return [(x0, y0), (x1, y0), (x1, y1 - cut), (x1 - cut, y1), (x0, y1)]


def _seneschal_cells() -> list[tuple[int, int, int, int]]:
    span = _SENESCHAL_RIGHT - _SENESCHAL_LEFT
    w = (span - 11 * _SENESCHAL_CELL_GAP) / 12
    cells = []
    for i in range(12):
        x0 = round(_SENESCHAL_LEFT + i * (w + _SENESCHAL_CELL_GAP))
        cells.append((x0, _SENESCHAL_CELL_TOP, round(x0 + w), _SENESCHAL_CELL_TOP + _SENESCHAL_CELL_H))
    return cells


def _seneschal_stipple(image: Image.Image, mask: Image.Image, accent: _SeneschalAccent, density: float,
                       *, over=None) -> None:
    """Stipple the accent into ``mask`` at ``density`` on the 8x8 tile, its
    minor ink taking the lowest ``share`` of the lit ranks so the hue holds
    (one read of the tile). ``over`` restricts it to pixels of those inks."""
    bbox = mask.getbbox()
    if bbox is None or density <= 0:
        return
    px, mp = pixel_access(image), gray_pixel_access(mask)
    major, minor = _seneschal_ink(accent.major), _seneschal_ink(accent.minor)
    lit = density * 64
    for y in range(bbox[1], bbox[3]):
        row = BAYER_8x8[y % 8]
        for x in range(bbox[0], bbox[2]):
            rank = row[x % 8]
            if mp[x, y] > 128 and rank < lit and (over is None or px[x, y] in over):
                px[x, y] = minor if minor is not None and rank < lit * accent.share else major


def _seneschal_mask(size, paint) -> Image.Image:
    mask = Image.new("L", size, 0)
    paint(ImageDraw.Draw(mask))
    return mask


# MARK: the ground


def _seneschal_scene_dark() -> Image.Image:
    """The navy: black with blue stippled in, thicker in a haze at the top
    and falling away into a vignette, every third row left black for the
    scanlines. Painted once per process."""
    cached = _SENESCHAL_SCENE.get("dark")
    if cached is not None:
        return cached
    size = (800, 480)
    density = Image.new("L", size, 0)
    dp = gray_pixel_access(density)
    for y in range(480):
        for x in range(800):
            dx, dy = (x - 400) / 400, (y - 240) / 240
            vignette = max(0.0, 1 - max(0.0, (dx * dx + dy * dy) ** 0.5 - 0.55) / 0.75)
            hx, hy = (x - 400) / 420, y / 260
            haze = max(0.0, 1 - (hx * hx + hy * hy) ** 0.5)
            dp[x, y] = round(255 * vignette * (0.13 + 0.17 * haze))
    lit = ImageChops.subtract(density, _bayer_threshold_field(size)).point(lambda v: 255 if v else 0)
    scan = Image.new("L", size, 255)
    sp = gray_pixel_access(scan)
    for y in range(0, 480, 3):
        for x in range(800):
            sp[x, y] = 0
    image = Image.new("RGB", size, SPECTRA6["black"])
    image.paste(SPECTRA6["blue"], (0, 0), ImageChops.multiply(lit, scan))
    for m in (density, lit, scan):
        m.close()
    _SENESCHAL_SCENE["dark"] = image
    return image


# MARK: the furniture


def _seneschal_paint_glyph(draw: ImageDraw.ImageDraw, kind: str, box, fill, width: int = 2) -> None:
    """The app's glyphs on its 24-unit grid, square-ended strokes: the gear,
    the power mark, the check seal and the bulb."""
    x0, y0, x1, y1 = box
    k = min(x1 - x0, y1 - y0) / 24

    def p(x: float, y: float) -> tuple[float, float]:
        return x0 + x * k, y0 + y * k

    if kind == "gear":
        rim = []
        for i in range(8):
            a = i * 45 - 90
            for r, d in ((8, -15), (10.5, -9), (10.5, 9), (8, 15)):
                rim.append(p(12 + r * math.cos(math.radians(a + d)), 12 + r * math.sin(math.radians(a + d))))
        draw.line([*rim, rim[0]], fill=fill, width=width)
        bore = [p(12 + 3.5 * math.cos(math.radians(i * 45 + 22.5)), 12 + 3.5 * math.sin(math.radians(i * 45 + 22.5)))
                for i in range(8)]
        draw.line([*bore, bore[0]], fill=fill, width=width)
    elif kind == "power":
        # Pillow's angles run clockwise from three o'clock: round from upper right to upper left.
        draw.arc((*p(4.5, 6), *p(19.5, 21)), start=-55, end=235, fill=fill, width=width)
        draw.line((p(12, 3), p(12, 12)), fill=fill, width=width)
    elif kind == "seal":
        octagon = [p(8, 2), p(16, 2), p(22, 8), p(22, 16), p(16, 22), p(8, 22), p(2, 16), p(2, 8)]
        draw.line([*octagon, octagon[0]], fill=fill, width=width)
        draw.line([p(7.5, 12), p(10.5, 15), p(16.5, 9)], fill=fill, width=width)
    elif kind == "bulb":
        body = [p(8, 2.5), p(16, 2.5), p(19, 5.5), p(19, 10.5), p(15, 14.5), p(15, 16.5),
                p(9, 16.5), p(9, 14.5), p(5, 10.5), p(5, 5.5)]
        draw.line([*body, body[0]], fill=fill, width=width)
        draw.line([p(10.5, 16.5), p(10.5, 10), p(12, 8.5), p(13.5, 10), p(13.5, 16.5)], fill=fill, width=width)
        draw.line((p(9, 19.5), p(15, 19.5)), fill=fill, width=width)
        draw.line((p(10.5, 22), p(13.5, 22)), fill=fill, width=width)


def _seneschal_hairline(image: Image.Image, points, ink, *, dotted: bool) -> None:
    """A one-pixel line: solid, or every other pixel for a quiet grey."""
    mask = _seneschal_mask(image.size, lambda d: d.line(points, fill=255, width=1))
    px, mp = pixel_access(image), gray_pixel_access(mask)
    bbox = mask.getbbox()
    if bbox:
        for y in range(bbox[1], bbox[3]):
            for x in range(bbox[0], bbox[2]):
                if mp[x, y] > 128 and (not dotted or (x + y) % 2 == 0):
                    px[x, y] = ink
    mask.close()


def _seneschal_paint_chrome(image: Image.Image, accent: _SeneschalAccent, *, dark: bool, on_now: int) -> None:
    """The wordmark and gear, the check line, On Now's label and All Off,
    and the Hours label."""
    draw = ImageDraw.Draw(image)
    text = SPECTRA6["white"] if dark else SPECTRA6["black"]
    black, blue = SPECTRA6["black"], SPECTRA6["blue"]
    left, right = _SENESCHAL_LEFT, _SENESCHAL_RIGHT

    # The wordmark, the one other use of the lit colour.
    mark = _seneschal_wide(21)
    if dark:
        mask = _seneschal_mask(image.size, lambda d: d.text((left, 31), "SENESCHAL", font=mark, fill=255))
        _seneschal_paint_hot(image, mask, accent, glow=True)
        mask.close()
    else:
        _seneschal_paint_deep_text(image, (left, 31), "SENESCHAL", mark, accent)
    _seneschal_paint_glyph(draw, "gear", (right - 20, 30, right, 50), text, width=2)
    _seneschal_hairline(image, [(left, 66), (right, 66)], blue if dark else black, dotted=not dark)

    # A clean check, in the interface's blue.
    _seneschal_paint_glyph(draw, "seal", (left, 80, left + 15, 95), blue if not dark else SPECTRA6["white"], width=1)
    draw_tracked(draw, (left + 24, 79), "ALL AS EXPECTED", _seneschal_cond(15), text, tracking=1.5)

    label = _seneschal_cond(15)
    for title, y in ((f"ON NOW  ·  {on_now}", 113), ("HOURS", 385)):
        draw.rectangle((left, y + 8, left + 11, y + 9), fill=text)
        draw_tracked(draw, (left + 22, y), title, label, text, tracking=2.6)

    off = _seneschal_cond(13, 700)
    width = tracked_width(draw, "ALL OFF", off, tracking=2)
    button = (round(right - width - 38), 106, right, 132)
    draw.line([*_seneschal_bevelled(button, 5), (button[0], button[1])], fill=text, width=1)
    _seneschal_paint_glyph(draw, "power", (button[0] + 9, 112, button[0] + 23, 126), text, width=2)
    draw_tracked(draw, (button[0] + 29, 111), "ALL OFF", off, text, tracking=2)


def _seneschal_paint_hot(image: Image.Image, mask: Image.Image, accent: _SeneschalAccent, *, glow: bool) -> None:
    """Text lit in the hot form of the accent on the dark panel: yellow's
    own ink, or white cores with a share of the darker inks (which read as
    unlit on black alone), in a bloom of the accent."""
    black, blue = SPECTRA6["black"], SPECTRA6["blue"]
    major, minor = _seneschal_ink(accent.major), _seneschal_ink(accent.minor)
    if accent.major == "yellow":
        core, core_minor, share = major, None, 0.0
    else:
        core, core_minor, share = SPECTRA6["white"], major, 0.3
    if glow:
        paint_neon_mask(image, mask, core, major, radius=2.5, gamma=1.7, cap=0.5, ground=(black, blue),
                        glow_minor=minor, glow_minor_share=accent.share, core_minor=core_minor, core_minor_share=share)
    else:
        paint_neon_mask(image, mask, core, major, radius=0.1, gamma=9, cap=0, ground=(),
                        core_minor=core_minor, core_minor_share=share)


def _seneschal_deep_inks(accent: _SeneschalAccent):
    """The accent taken deep for text on the light panel, as the app does:
    the darker inks as they are (mixes as a stipple of their two), and gold
    as black with yellow in it."""
    if accent.major == "yellow":
        return SPECTRA6["black"], SPECTRA6["yellow"], 0.25
    if accent.minor is None or accent.minor == "yellow":
        return _seneschal_ink(accent.major), None, 0.0
    return _seneschal_ink(accent.major), _seneschal_ink(accent.minor), 0.5


def _seneschal_paint_deep_text(image: Image.Image, xy, text: str, font, accent: _SeneschalAccent) -> None:
    dark, light, density = _seneschal_deep_inks(accent)
    if light is None:
        ImageDraw.Draw(image).text(xy, text, font=font, fill=dark)
    else:
        draw_text_dithered(image, xy, text, font, dark=dark, light=light, light_density=density)


# MARK: panels


def _seneschal_paint_panel(image: Image.Image, rect, accent: _SeneschalAccent, *, lit: bool, dark: bool,
                           cut: int, marker: int, wash: float) -> None:
    """A HUD panel. Dark and lit: an outline in the accent blooming onto the
    ground, a faint wash of it inside falling away to the right, and a
    marker down the left edge. Dark and unlit: a black well with a blue edge.
    Light and lit: the accent stippled over the white at ``wash``, pressed in
    by a shadow inside along the top and left. Light and unlit: flush, a
    grey hairline."""
    draw = ImageDraw.Draw(image)
    shape = _seneschal_bevelled(rect, cut)
    black, white, blue = SPECTRA6["black"], SPECTRA6["white"], SPECTRA6["blue"]
    major = _seneschal_ink(accent.major)
    x0, y0, x1, y1 = rect
    if dark:
        draw.polygon(shape, fill=black)
        if not lit:
            draw.line([*shape, shape[0]], fill=blue, width=1)
            return
        inside = _seneschal_mask(image.size, lambda d: d.polygon(shape, fill=255))
        fade = Image.linear_gradient("L").rotate(90, expand=True).resize((x1 - x0, y1 - y0))
        fade = fade.point(lambda v: round(v * 0.14))
        density = Image.new("L", image.size, 0)
        density.paste(fade, (x0, y0))
        lit_px = ImageChops.subtract(density, _bayer_threshold_field(image.size)).point(lambda v: 255 if v else 0)
        _seneschal_stipple(image, ImageChops.multiply(inside, lit_px), accent, 1.0)
        outline = _seneschal_mask(image.size, lambda d: d.line([*shape, shape[0]], fill=255, width=2))
        paint_neon_mask(image, outline, major, major, radius=3, gamma=1.8, cap=0.45, ground=(black, blue),
                        glow_minor=_seneschal_ink(accent.minor), glow_minor_share=accent.share)
        draw.rectangle((x0, y0, x0 + marker - 1, y1), fill=major)
        for m in (inside, fade, density, lit_px, outline):
            m.close()
        return
    if not lit:
        _seneschal_hairline(image, [*shape, shape[0]], black, dotted=True)
        return
    inside = _seneschal_mask(image.size, lambda d: d.polygon(shape, fill=255))
    _seneschal_stipple(image, inside, accent, wash, over=(white,))
    # Pressed in: black falling away from the top and left edges inside.
    px = pixel_access(image)
    for depth, shade in ((0, 0.75), (1, 0.5), (2, 0.25), (3, 0.125)):
        for x in range(x0, x1 - cut if depth else x1):
            if BAYER_8x8[(y0 + depth) % 8][x % 8] < shade * 64:
                px[x, y0 + depth] = black
        for y in range(y0, y1):
            if BAYER_8x8[y % 8][(x0 + depth) % 8] < shade * 64:
                px[x0 + depth, y] = black
    _seneschal_hairline(image, [*shape, shape[0]], black, dotted=True)
    inside.close()


def _seneschal_paint_cells(image: Image.Image, accent: _SeneschalAccent, hour: int | None, *, dark: bool) -> None:
    """The Hours strip: twelve 1U cells, the hour's lit."""
    draw = ImageDraw.Draw(image)
    for i, rect in enumerate(_seneschal_cells(), start=1):
        lit = i == hour
        _seneschal_paint_panel(image, rect, accent, lit=lit, dark=dark, cut=6, marker=3, wash=1.0)
        font = _seneschal_cond(19, 700 if lit else 600)
        label = str(i)
        w = draw.textlength(label, font=font)
        xy = ((rect[0] + rect[2] - w) / 2, rect[1] + 8)
        if not lit:
            draw.text(xy, label, font=font, fill=SPECTRA6["white"] if dark else SPECTRA6["black"])
        elif dark:
            mask = _seneschal_mask(image.size, lambda d, xy=xy, label=label, font=font: d.text(xy, label, font=font, fill=255))
            _seneschal_paint_hot(image, mask, accent, glow=True)
            mask.close()
        else:
            # On the lit fill: black on yellow, white on the darker inks.
            ink = SPECTRA6["black"] if accent.major == "yellow" else SPECTRA6["white"]
            draw.text(xy, label, font=font, fill=ink)


# MARK: the words


def _seneschal_byline(quote_row: dict) -> str:
    author = (quote_row.get("author") or "").strip()
    title = (quote_row.get("title") or "").strip() or (fallback_title(quote_row) or "").strip()
    return "  ·  ".join(p.upper() for p in (author, title) if p) or "PROJECT GUTENBERG"


def _seneschal_paint_words(image: Image.Image, quote_row: dict, accent: _SeneschalAccent, *, dark: bool, lit: bool,
                           theme: str) -> None:
    """The bulb, the quote and the byline in On Now's panel. Lit, the bulb
    and the phrase take the accent; unlit (the sleep frame) they keep to the
    text colour."""
    draw = ImageDraw.Draw(image)
    text = SPECTRA6["white"] if dark else SPECTRA6["black"]
    bulb_box = (62, 166, 90, 194)
    prose, hot, _ = wrap_quote_into_masks(draw, image.size, quote_row, _SENESCHAL_QUOTE_RECT, theme=theme,
                                          font_max=32, font_min=15, line_height_mult=1.3, align="left")
    image.paste(text, (0, 0), prose)
    bulb = _seneschal_mask(image.size, lambda d: _seneschal_paint_glyph(d, "bulb", bulb_box, 255, width=2))
    if not lit:
        image.paste(text, (0, 0), hot)
        image.paste(text, (0, 0), bulb)
    elif dark:
        _seneschal_paint_hot(image, hot, accent, glow=True)
        _seneschal_paint_hot(image, bulb, accent, glow=True)
    else:
        deep, light, density = _seneschal_deep_inks(accent)
        for mask in (hot, bulb):
            px, mp = pixel_access(image), gray_pixel_access(mask)
            bbox = mask.getbbox()
            if bbox:
                for y in range(bbox[1], bbox[3]):
                    for x in range(bbox[0], bbox[2]):
                        if mp[x, y] > 128:
                            use_light = light is not None and BAYER_8x8[y % 8][x % 8] < density * 64
                            px[x, y] = light if use_light else deep
    for m in (prose, hot, bulb):
        m.close()
    font = _seneschal_cond(16, 700)
    byline = _seneschal_byline(quote_row)
    max_w = _SENESCHAL_QUOTE_RECT[2] - _SENESCHAL_QUOTE_RECT[0]
    while len(byline) > 2 and tracked_width(draw, byline, font, tracking=1.6) > max_w:
        byline = byline[:-2].rstrip(" ·,.;:") + "…"
    if lit and dark:
        # The darker inks are dim on black at this size, and a stipple shreds it: white, but for gold.
        ink = SPECTRA6["yellow"] if accent.major == "yellow" else SPECTRA6["white"]
    elif lit:
        # Solid, as small caps must be: the accent's own ink where it has one, else black.
        deep, light, _ = _seneschal_deep_inks(accent)
        ink = deep if light is None else SPECTRA6["black"]
    else:
        ink = text
    draw_tracked(draw, (_SENESCHAL_QUOTE_RECT[0], _SENESCHAL_BYLINE_Y), byline, font, ink, tracking=1.6)


# MARK: the screen


def _seneschal_compose(image: Image.Image, quote_row: dict, hour: int | None, *, dark: bool, theme: str) -> Image.Image:
    """Everything over the ground, then the snap to the panel's inks. ``hour``
    is the one lit (and picks the accent); ``None`` is the sleep frame, with
    nothing on."""
    accent = _seneschal_accent(hour or 12)
    lit = hour is not None
    _seneschal_paint_chrome(image, accent, dark=dark, on_now=1 if lit else 0)
    _seneschal_paint_panel(image, _SENESCHAL_PANEL, accent, lit=lit, dark=dark, cut=_SENESCHAL_PANEL_CUT,
                           marker=4, wash=0.25 if accent.major != "yellow" else 0.375)
    _seneschal_paint_words(image, quote_row, accent, dark=dark, lit=lit, theme=theme)
    _seneschal_paint_cells(image, accent, hour, dark=dark)
    return image


def _seneschal_finish(image: Image.Image, width: int, height: int) -> Image.Image:
    image = snap_image_to_palette(image, SPECTRA6_PALETTE)
    if (width, height) != (800, 480):
        image = image.resize((width, height), Image.Resampling.NEAREST)
    return image
