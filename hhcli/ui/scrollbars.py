from __future__ import annotations
from math import floor

from rich.color import Color
from rich.segment import Segment, Segments
from rich.style import Style

from textual.scrollbar import ScrollBarRender


class ThinScrollBarRender(ScrollBarRender):
    """Рендер полос прокрутки, который рисует более тонкие глифы внутри ячейки."""

    HORIZONTAL_GLYPH = "▂"
    VERTICAL_GLYPH = "▋"

    @classmethod
    def render_bar(
        cls,
        size: int = 25,
        virtual_size: float = 50,
        window_size: float = 20,
        position: float = 0,
        thickness: int = 1,
        vertical: bool = True,
        back_color: Color | None = None,
        bar_color: Color | None = None,
    ) -> Segments:
        size = int(size)
        back = None
        bar = bar_color or Color.parse("bright_magenta")
        glyph = cls.VERTICAL_GLYPH if vertical else cls.HORIZONTAL_GLYPH
        width_thickness = thickness if vertical else 1
        blank = " " * width_thickness

        _Segment = Segment
        _Style = Style
        foreground_meta = {"@mouse.down": "grab"}
        upper = {"@mouse.up": "scroll_up"}
        lower = {"@mouse.up": "scroll_down"}

        def make_blank(meta):
            return _Segment(blank, _Style(bgcolor=None, meta=meta))

        if not (
            window_size
            and size
            and virtual_size
            and size < virtual_size
            and virtual_size > window_size
        ):
            segments = [make_blank(upper)] * size
        else:
            bar_ratio = virtual_size / size
            thumb_size = max(1.0, window_size / bar_ratio)
            position_ratio = position / (virtual_size - window_size)
            start_float = (size - thumb_size) * position_ratio
            thumb_start = max(0, min(size - 1, int(floor(start_float))))
            thumb_end = max(
                thumb_start + 1,
                min(size, int(thumb_start + thumb_size)),
            )

            segments: list[Segment] = []
            for index in range(size):
                if index < thumb_start:
                    segments.append(make_blank(upper))
                elif index >= thumb_end:
                    segments.append(make_blank(lower))
                else:
                    char = glyph * width_thickness if vertical else glyph
                    segments.append(
                        _Segment(
                            char,
                            _Style(
                                bgcolor=back,
                                color=bar,
                                meta=foreground_meta,
                            ),
                        )
                    )

        if vertical:
            return Segments(segments, new_lines=True)

        horizontal_line = segments + [_Segment.line()]
        return Segments(horizontal_line * thickness, new_lines=False)
