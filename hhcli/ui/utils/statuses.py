from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from ...constants import (
    ApiErrorReason,
    DELIVERED_STATUS_CODES,
    ERROR_REASON_LABELS,
    FAILED_STATUS_CODES,
)
from .formatting import normalize

IGNORED_AFTER_DAYS = 4

FAILED_REASON_SHORT_LABELS: dict[str, str] = {
    ApiErrorReason.TEST_REQUIRED: "Тест",
    ApiErrorReason.QUESTIONS_REQUIRED: "Вопросы",
    ApiErrorReason.ALREADY_APPLIED: "Дубль",
    ApiErrorReason.NEGOTIATIONS_FORBIDDEN: "Запрет",
    ApiErrorReason.RESUME_NOT_PUBLISHED: "Резюме",
    ApiErrorReason.CONDITIONS_NOT_MET: "Не подходит",
    ApiErrorReason.NOT_FOUND: "Архив",
    ApiErrorReason.BAD_ARGUMENT: "Ошибка",
    ApiErrorReason.UNKNOWN_API_ERROR: "Ошибка",
    ApiErrorReason.NETWORK_ERROR: "Сеть",
}

STATUS_DISPLAY_MAP: dict[str, str] = {
    "applied": "Отклик",
    "invited": "Собес",
    "interview": "Собес",
    "interview_assigned": "Собес",
    "interview_scheduled": "Собес",
    "offer": "Оффер",
    "offer_made": "Оффер",
    "rejected": "Отказ",
    "declined": "Отказ",
    "canceled": "Отказ",
    "cancelled": "Отказ",
    "discard": "Отказ",
    "employer_viewed": "Просмотр",
    "viewed": "Просмотр",
    "seen": "Просмотр",
    "in_progress": "В работе",
    "considering": "В работе",
    "processing": "В работе",
    "responded": "Ответ",
    "response": "Отклик",
    "answered": "Ответ",
    "ignored": "Игнор",
    "hired": "Выход",
    "accepted": "Принят",
    "test_required": "Тест",
    "questions_required": "Вопросы",
}


def normalize_status_code(status: Optional[str]) -> str:
    return (status or "").strip().lower()


def normalize_reason_code(reason: Optional[str]) -> str:
    return (reason or "").strip().lower()


def _now_for(dt: datetime) -> datetime:
    return datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()


def is_ignored(applied_at: Optional[datetime]) -> bool:
    if not isinstance(applied_at, datetime):
        return False
    return (_now_for(applied_at) - applied_at) > timedelta(days=IGNORED_AFTER_DAYS)


def is_delivered(status: Optional[str]) -> bool:
    code = normalize_status_code(status)
    if not code:
        return False
    if code in FAILED_STATUS_CODES:
        return False
    if code in DELIVERED_STATUS_CODES:
        return True
    for prefix in ("applied", "response", "responded", "invited", "offer"):
        if code.startswith(prefix):
            return True
    return False


def is_failed(status: Optional[str]) -> bool:
    code = normalize_status_code(status)
    return code in FAILED_STATUS_CODES


def format_history_status(
    status: Optional[str],
    reason: Optional[str],
    applied_at: Optional[datetime],
) -> str:
    code = normalize_status_code(status)
    if not code:
        return "-"

    if code == "failed":
        reason_code = normalize_reason_code(reason)
        if reason_code in FAILED_REASON_SHORT_LABELS:
            return FAILED_REASON_SHORT_LABELS[reason_code]
        if reason_code in ERROR_REASON_LABELS:
            return ERROR_REASON_LABELS[reason_code]
        return reason or "Ошибка"

    if code in {"applied", "response"}:
        if is_ignored(applied_at):
            return STATUS_DISPLAY_MAP.get("ignored", "Игнор")
        return STATUS_DISPLAY_MAP.get(code, "Отклик")

    if code in STATUS_DISPLAY_MAP:
        return STATUS_DISPLAY_MAP[code]

    if status:
        return str(status).replace("_", " ").title()
    return "-"


def collect_delivered(history: list[dict]) -> tuple[set[str], set[str], set[str]]:
    """Возвращает кортеж из id доставленных вакансий, ключей title|employer и нормализованных названий компаний"""
    processed_vacancies: dict[str, dict] = {}

    for h in history:
        vid = str(h.get("vacancy_id") or "")
        if not vid:
            continue

        status = h.get("status")
        updated_at = h.get("applied_at")

        if vid not in processed_vacancies:
            processed_vacancies[vid] = {
                "last_status": status,
                "last_updated_at": updated_at,
                "has_been_delivered": is_delivered(status),
                "title": h.get("vacancy_title"),
                "employer": h.get("employer_name"),
            }
        else:
            if updated_at and processed_vacancies[vid]["last_updated_at"]:
                if updated_at > processed_vacancies[vid]["last_updated_at"]:
                    processed_vacancies[vid]["last_status"] = status
                    processed_vacancies[vid]["last_updated_at"] = updated_at
            elif updated_at:
                processed_vacancies[vid]["last_status"] = status
                processed_vacancies[vid]["last_updated_at"] = updated_at

            if not processed_vacancies[vid]["has_been_delivered"] and is_delivered(status):
                processed_vacancies[vid]["has_been_delivered"] = True

    delivered_ids: set[str] = set()
    delivered_keys: set[str] = set()
    delivered_employers: set[str] = set()

    for vid, data in processed_vacancies.items():
        is_successfully_delivered = (
            data["has_been_delivered"] and not is_failed(data["last_status"])
        )
        if is_successfully_delivered:
            delivered_ids.add(vid)

            title = normalize(data["title"])
            employer = normalize(data["employer"])

            key = f"{title}|{employer}"
            if key.strip("|"):
                delivered_keys.add(key)

            if employer:
                delivered_employers.add(employer)

    return delivered_ids, delivered_keys, delivered_employers


__all__ = [
    "FAILED_REASON_SHORT_LABELS",
    "IGNORED_AFTER_DAYS",
    "STATUS_DISPLAY_MAP",
    "collect_delivered",
    "format_history_status",
    "is_delivered",
    "is_failed",
    "is_ignored",
    "normalize_reason_code",
    "normalize_status_code",
]
