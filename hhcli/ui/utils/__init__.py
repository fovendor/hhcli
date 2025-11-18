"""Утилиты для UI"""

from .formatting import (
    clamp,
    format_date,
    format_datetime,
    format_segment,
    normalize,
    normalize_width_map,
    set_loader_visible,
)
from .statuses import (
    FAILED_REASON_SHORT_LABELS,
    IGNORED_AFTER_DAYS,
    STATUS_DISPLAY_MAP,
    collect_delivered,
    format_history_status,
    is_delivered,
    is_failed,
    is_ignored,
    normalize_reason_code,
    normalize_status_code,
)

__all__ = [
    "FAILED_REASON_SHORT_LABELS",
    "IGNORED_AFTER_DAYS",
    "STATUS_DISPLAY_MAP",
    "clamp",
    "collect_delivered",
    "format_date",
    "format_datetime",
    "format_history_status",
    "format_segment",
    "is_delivered",
    "is_failed",
    "is_ignored",
    "normalize",
    "normalize_reason_code",
    "normalize_status_code",
    "normalize_width_map",
    "set_loader_visible",
]
