"""The ``goodmountain`` theme: a quest-giver's parchment set in Goodmountain.

Design notes: docs/themes.md § goodmountain
"""

from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw

from .._paths import GOODMOUNTAIN_REGULAR, ORNAMENT_FONT_CANDIDATES
from ..fonts import load_font
from ..furniture import _paint_placed, _place_quote, _row_digest, fallback_title
from ..palette import SPECTRA6, SPECTRA6_PALETTE, snap_image_to_palette
from ..primitives import _smooth_noise, _white_noise
from ..spec import FrameSpec
from ..text import fit_text_to_width

_GOODMOUNTAIN_SEED = 0x474D544E            # GMTN
_GOODMOUNTAIN_SHEET = (24, 20, 776, 460)   # the parchment, before its edge is torn
_GOODMOUNTAIN_TITLE_Y = 54                 # centre line of the quest title
_GOODMOUNTAIN_TITLE_MAX_W = 580
_GOODMOUNTAIN_MARKER = (72, 60)            # centre of the quest giver's mark
_GOODMOUNTAIN_RULE_Y = 92
_GOODMOUNTAIN_BODY = (68, 112, 732, 326)
_GOODMOUNTAIN_DIVIDER_Y = 340
_GOODMOUNTAIN_FOOT_Y = 352                 # top of the two foot headings
_GOODMOUNTAIN_GIVER_X = 68
_GOODMOUNTAIN_REWARDS_X = 492
_GOODMOUNTAIN_SLOT = 58                    # reward slot, outer edge
_GOODMOUNTAIN_SLOT_GAP = 22
# The rewards: pictograms from the face's own emoji slots, each in the ink
# it reads best in on a black slot.
_GOODMOUNTAIN_REWARDS = (
    ("\U0001FA99", "yellow"),   # coin
    ("\U0001F48E", "blue"),     # gem
    ("\U0001F4DC", "yellow"),   # scroll
    ("\U0001F4D6", "white"),    # open book
    ("\U0001F528", "white"),    # hammer
    ("\U0001F56F", "yellow"),   # candle
    ("\U0001F5E1", "white"),    # dagger
    ("\U0001F6E1", "red"),      # shield
    ("\U0001FA93", "white"),    # axe
    ("\U0001F50B", "red"),      # potion
    ("\U0001FA84", "yellow"),   # wand
    ("\U0001FA8E", "yellow"),   # chest
    ("\U0001F451", "white"),    # helm
    ("\U0001F3B2", "white"),    # die
)
# Slot rims in item-quality order: uncommon, rare, legendary.
_GOODMOUNTAIN_RARITY = ("green", "blue", "yellow")


def _goodmountain_font(size: int):
    return load_font([GOODMOUNTAIN_REGULAR, *ORNAMENT_FONT_CANDIDATES], size=size)


def _goodmountain_paint_sheet(image: Image.Image) -> None:
    """The parchment: a Y+W cream from an aperiodic stipple, deepening
    toward a torn edge that is scorched red where it meets the dark."""
    size = image.size
    x0, y0, x1, y1 = _GOODMOUNTAIN_SHEET
    # Distance in from the sheet's edge, in px, clamped at 40.
    inset = Image.new("L", size, 0)
    d = ImageDraw.Draw(inset)
    for i in range(41):
        d.rectangle((x0 + i, y0 + i, x1 - i, y1 - i), fill=i * 6)
    tear = _smooth_noise(size, (80, 48), _GOODMOUNTAIN_SEED)
    stain = _smooth_noise(size, (10, 6), _GOODMOUNTAIN_SEED + 1)
    # The torn edge: a pixel is on the sheet once its inset beats the tear noise.
    on_sheet = ImageChops.subtract(inset, tear.point(lambda v: 8 + v // 6)).point(lambda v: 255 if v else 0)
    # Scorch: the first few px inside the tear.
    scorch = ImageChops.subtract(inset, tear.point(lambda v: 26 + v // 6)).point(lambda v: 0 if v else 255)
    scorch = ImageChops.multiply(scorch, on_sheet)
    # Cream density: a light base, mottled stains, rising toward the edge.
    edge = inset.point(lambda v: max(0, 240 - v))
    density = ImageChops.add(stain.point(lambda v: 72 + v // 4), edge.point(lambda v: v * 2 // 3))
    yellow = ImageChops.subtract(density, _white_noise(*size, _GOODMOUNTAIN_SEED + 2)).point(lambda v: 255 if v else 0)
    image.paste(SPECTRA6["white"], (0, 0), on_sheet)
    image.paste(SPECTRA6["yellow"], (0, 0), ImageChops.multiply(yellow, on_sheet))
    burnt = ImageChops.subtract(Image.new("L", size, 150), _white_noise(*size, _GOODMOUNTAIN_SEED + 3))
    image.paste(SPECTRA6["red"], (0, 0), ImageChops.multiply(scorch, burnt.point(lambda v: 255 if v else 0)))
    for m in (inset, tear, stain, on_sheet, scorch, edge, density, yellow, burnt):
        m.close()


def _goodmountain_paint_brackets(draw: ImageDraw.ImageDraw) -> None:
    """Iron corner brackets with gold rivets, holding the sheet down."""
    black, yellow = SPECTRA6["black"], SPECTRA6["yellow"]
    arm, thick = 46, 12
    for cx, cy, sx, sy in ((8, 8, 1, 1), (791, 8, -1, 1), (8, 471, 1, -1), (791, 471, -1, -1)):
        for w, h in ((arm, thick), (thick, arm)):
            xa, xb = sorted((cx, cx + sx * w))
            ya, yb = sorted((cy, cy + sy * h))
            draw.rectangle((xa, ya, xb, yb), fill=black, outline=yellow, width=2)
        for dx, dy in ((7, 6), (arm - 8, 6), (6, arm - 8)):
            rx, ry = cx + sx * dx, cy + sy * dy
            draw.ellipse((rx - 3, ry - 3, rx + 3, ry + 3), fill=yellow)


def _goodmountain_paint_title(draw: ImageDraw.ImageDraw, quote_row: dict) -> None:
    """The quest's name, the book, over a rule broken by crossed swords."""
    black, red = SPECTRA6["black"], SPECTRA6["red"]
    title = (quote_row.get("title") or "").strip() or (fallback_title(quote_row) or "").strip() or "An Untitled Errand"
    # A quest has a short name: drop a subtitle that would push the title
    # under the floor size.
    main = title.split(":")[0].split(";")[0].strip()
    if main and draw.textlength(title, font=_goodmountain_font(28)) > _GOODMOUNTAIN_TITLE_MAX_W:
        title = main
    font, text = fit_text_to_width(draw, title, [GOODMOUNTAIN_REGULAR, *ORNAMENT_FONT_CANDIDATES], 40,
                                   _GOODMOUNTAIN_TITLE_MAX_W, floor=24)
    draw.text((400, _GOODMOUNTAIN_TITLE_Y), text, font=font, fill=black, anchor="mm")
    y = _GOODMOUNTAIN_RULE_Y
    swords = _goodmountain_font(26)
    half = draw.textlength("⚔", font=swords) / 2 + 10
    draw.line((150, y, 400 - half, y), fill=black, width=2)
    draw.line((400 + half, y, 650, y), fill=black, width=2)
    for x in (146, 654):
        draw.polygon([(x - 5, y), (x, y - 5), (x + 5, y), (x, y + 5)], fill=red)
    draw.text((400, y), "⚔", font=swords, fill=red, anchor="mm")


def _goodmountain_paint_marker(draw: ImageDraw.ImageDraw) -> None:
    """The quest giver's mark: a gold exclamation point, outlined black."""
    draw.text(_GOODMOUNTAIN_MARKER, "!", font=_goodmountain_font(64), fill=SPECTRA6["yellow"], anchor="mm",
              stroke_width=3, stroke_fill=SPECTRA6["black"])


def _goodmountain_paint_giver(draw: ImageDraw.ImageDraw, quote_row: dict) -> None:
    """The author as the quest giver, under a red heading."""
    x, y = _GOODMOUNTAIN_GIVER_X, _GOODMOUNTAIN_FOOT_Y
    draw.text((x, y), "Quest Giver", font=_goodmountain_font(22), fill=SPECTRA6["red"])
    giver = (quote_row.get("author") or "").strip() or "A Stranger"
    font, text = fit_text_to_width(draw, giver, [GOODMOUNTAIN_REGULAR, *ORNAMENT_FONT_CANDIDATES], 36,
                                   _GOODMOUNTAIN_REWARDS_X - x - 32, floor=20)
    draw.text((x, y + 34), text, font=font, fill=SPECTRA6["black"])


def _goodmountain_rewards(quote_row: dict) -> list[tuple[str, str]]:
    """Three distinct rewards, seeded from the row."""
    seed = _row_digest(quote_row)
    pool = list(_GOODMOUNTAIN_REWARDS)
    picks = []
    for _ in range(3):
        picks.append(pool.pop(seed % len(pool)))
        seed //= len(_GOODMOUNTAIN_REWARDS)
    return picks


def _goodmountain_paint_rewards(draw: ImageDraw.ImageDraw, quote_row: dict) -> None:
    """Rewards: three item slots, rimmed by quality, each holding a pictogram."""
    x, y = _GOODMOUNTAIN_REWARDS_X, _GOODMOUNTAIN_FOOT_Y
    draw.text((x, y), "Rewards", font=_goodmountain_font(22), fill=SPECTRA6["red"])
    icon = _goodmountain_font(60)
    top = y + 34
    for i, ((glyph, ink), rim) in enumerate(zip(_goodmountain_rewards(quote_row), _GOODMOUNTAIN_RARITY, strict=True)):
        sx = x + i * (_GOODMOUNTAIN_SLOT + _GOODMOUNTAIN_SLOT_GAP)
        box = (sx, top, sx + _GOODMOUNTAIN_SLOT - 1, top + _GOODMOUNTAIN_SLOT - 1)
        draw.rectangle(box, fill=SPECTRA6["black"], outline=SPECTRA6[rim], width=3)
        draw.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), glyph, font=icon, fill=SPECTRA6[ink], anchor="mm")


def render_goodmountain_frame(time_str: str, quote_row: dict, width: int, height: int) -> Image.Image:
    """A quest-giver's parchment (see docs/themes.md)."""
    del time_str
    image = Image.new("RGB", (800, 480), SPECTRA6["black"])
    _goodmountain_paint_sheet(image)
    draw = ImageDraw.Draw(image)
    _goodmountain_paint_brackets(draw)
    _goodmountain_paint_title(draw, quote_row)
    _goodmountain_paint_marker(draw)
    placed = _place_quote(draw, quote_row, _GOODMOUNTAIN_BODY, theme="goodmountain",
                          font_max=48, font_min=16, line_height_mult=1.3)
    if placed:
        # Centre the block in the body rect: a short quote sits mid-page.
        x0, y0, x1, y1 = _GOODMOUNTAIN_BODY
        used = placed[-1][1] - placed[0][1] + placed[-1][6]
        dy = max(0, (y1 - y0 - used) // 2)
        placed = [(x, y + dy, *rest) for x, y, *rest in placed]
    _paint_placed(draw, placed, SPECTRA6["black"], SPECTRA6["red"])
    y = _GOODMOUNTAIN_DIVIDER_Y
    draw.line((_GOODMOUNTAIN_GIVER_X, y, 800 - _GOODMOUNTAIN_GIVER_X, y), fill=SPECTRA6["black"], width=1)
    _goodmountain_paint_giver(draw, quote_row)
    _goodmountain_paint_rewards(draw, quote_row)
    image = snap_image_to_palette(image, SPECTRA6_PALETTE)
    if (width, height) != (800, 480):
        image = image.resize((width, height), Image.Resampling.NEAREST)
    return image


SPEC = FrameSpec(themes=("goodmountain",), render=render_goodmountain_frame)
