from __future__ import annotations

from datetime import datetime
from typing import Optional

from rich.text import Text
from textual.screen import Screen
from textual.widgets import LoadingIndicator


def clamp(value: int, min_value: int, max_value: int) -> int:
    """Ограничивает значение заданным диапазоном"""
    return max(min_value, min(max_value, value))


def normalize_width_map(
    width_map: dict[str, int],
    order: list[str],
    *,
    max_value: int | None = None,
) -> dict[str, int]:
    """Приводит сохранённые ширины к допустимому диапазону"""
    normalized: dict[str, int] = {}
    for key in order:
        raw = width_map.get(key, 0)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 0
        normalized_value = max(1, value)
        if max_value is not None:
            normalized_value = min(max_value, normalized_value)
        normalized[key] = normalized_value
    return normalized


def normalize(text: Optional[str]) -> str:
    """Приводит строку к нижнему регистру и удаляет лишние пробелы"""
    if not text:
        return ""
    return " ".join(str(text).lower().split())


def format_datetime(value: datetime | str | None) -> str:
    """Форматирует дату и время в человекочитаемую строку"""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return value
    return "-"


def format_date(value: datetime | str | None) -> str:
    """Возвращает строковое представление даты без времени"""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return value.split(" ")[0]
    return "-"


def set_loader_visible(container: Screen, loader_id: str, visible: bool) -> None:
    """Переключает видимость индикатора загрузки по идентификатору"""
    container.query_one(f"#{loader_id}", LoadingIndicator).display = visible


def format_segment(
    content: str | None,
    width: int,
    *,
    style: str | None = None,
    strike: bool = False,
) -> Text:
    """Форматирует сегмент строки таблицы с учётом ширины"""
    segment = Text(content or "", no_wrap=True, overflow="ellipsis")
    segment.truncate(width, overflow="ellipsis")
    if strike:
        segment.stylize("strike", 0, len(segment))
    if style:
        segment.stylize(style, 0, len(segment))
    padding = max(0, width - segment.cell_len)
    if padding:
        segment.append(" " * padding)
    return segment


__all__ = [
    "format_segment",
    "clamp",
    "format_date",
    "format_datetime",
    "normalize",
    "normalize_width_map",
    "set_loader_visible",
]
