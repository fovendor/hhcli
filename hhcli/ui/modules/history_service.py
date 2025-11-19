from __future__ import annotations


from ...database import (
    get_full_negotiation_history_for_profile,
    get_negotiation_history_for_resume,
)
from ..utils.statuses import collect_delivered, format_history_status


def load_delivery_summary(profile_name: str) -> tuple[set[str], set[str], set[str]]:
    """Возвращает наборы доставленных вакансий, ключей и компаний"""
    history = get_full_negotiation_history_for_profile(profile_name)
    return collect_delivered(history)


def fetch_resume_history(profile_name: str, resume_id: str) -> list[dict]:
    """Загружает историю откликов по резюме и подставляет человекочитаемые статусы"""
    raw_entries = get_negotiation_history_for_resume(profile_name, resume_id)

    entries: list[dict] = []
    for item in raw_entries:
        display_status = format_history_status(
            item.get("status"),
            item.get("reason"),
            item.get("applied_at"),
        )
        enriched = dict(item)
        enriched["status_display"] = display_status
        enriched["sent_display"] = "да" if bool(item.get("was_delivered")) else "нет"
        entries.append(enriched)
    return entries


__all__ = [
    "fetch_resume_history",
    "load_delivery_summary",
]
