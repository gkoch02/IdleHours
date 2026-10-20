"""The ``seneschal_light`` theme: Seneschal's main screen on its daylight panel.

Design notes: docs/themes.md § seneschal
"""

from __future__ import annotations

from PIL import Image

from ..furniture import _clock_hour12
from ..palette import SPECTRA6
from ..spec import FrameSpec
from ._seneschal_common import _SENESCHAL_SLEEP_ROW, _seneschal_compose, _seneschal_finish


def _seneschal_light_paint_screen(image: Image.Image, quote_row: dict, hour: int | None) -> None:
    """The screen over the white: on pressed in and filled, off flush."""
    _seneschal_compose(image, quote_row, hour, dark=False, theme="seneschal_light")


def render_seneschal_light_frame(time_str: str, quote_row: dict, width: int, height: int) -> Image.Image:
    """The daylight panel: the quote in On Now's lit panel, the hour lit in
    the Hours strip, the lit colour the hour's (see docs/themes.md)."""
    image = Image.new("RGB", (800, 480), SPECTRA6["white"])
    _seneschal_light_paint_screen(image, quote_row, _clock_hour12(time_str))
    return _seneschal_finish(image, width, height)


def render_seneschal_light_sleep(time_str: str, width: int, height: int) -> Image.Image:
    """The quiet-hours frame, as ``seneschal``'s: nothing on. ``time_str`` is unused."""
    del time_str
    image = Image.new("RGB", (800, 480), SPECTRA6["white"])
    _seneschal_light_paint_screen(image, _SENESCHAL_SLEEP_ROW, None)
    return _seneschal_finish(image, width, height)


SPEC = FrameSpec(themes=("seneschal_light",), render=render_seneschal_light_frame, sleep=render_seneschal_light_sleep)
