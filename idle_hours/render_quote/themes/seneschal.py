"""The ``seneschal`` theme: Seneschal's main screen in its dark HUD, the quote the one thing on.

Design notes: docs/themes.md § seneschal
"""

from __future__ import annotations

from PIL import Image

from ..furniture import _clock_hour12
from ..spec import FrameSpec
from ._seneschal_common import _SENESCHAL_SLEEP_ROW, _seneschal_compose, _seneschal_finish, _seneschal_scene_dark


def render_seneschal_frame(time_str: str, quote_row: dict, width: int, height: int) -> Image.Image:
    """The HUD: the quote in On Now's lit panel, the hour lit in the Hours
    strip, the lit colour the hour's (see docs/themes.md)."""
    image = _seneschal_compose(_seneschal_scene_dark().copy(), quote_row, _clock_hour12(time_str), dark=True,
                               theme="seneschal")
    return _seneschal_finish(image, width, height)


def render_seneschal_sleep(time_str: str, width: int, height: int) -> Image.Image:
    """The quiet-hours frame: All Off has run. On Now is empty, its panel
    unlit with a note in it, and no hour is lit. ``time_str`` is unused."""
    del time_str
    image = _seneschal_compose(_seneschal_scene_dark().copy(), _SENESCHAL_SLEEP_ROW, None, dark=True, theme="seneschal")
    return _seneschal_finish(image, width, height)


SPEC = FrameSpec(themes=("seneschal",), render=render_seneschal_frame, sleep=render_seneschal_sleep)
