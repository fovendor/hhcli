from __future__ import annotations

import html

from ...constants import ERROR_REASON_LABELS
from ..utils.formatting import format_datetime
from ..utils.statuses import (
    format_history_status,
    normalize_reason_code,
    normalize_status_code,
)


def _format_salary_line(salary_data: dict | None) -> str:
    if not salary_data:
        return "N/A"
    s_from = salary_data.get("from")
    s_to = salary_data.get("to")
    currency = (salary_data.get("currency") or "").upper()
    gross_str = " (до вычета налогов)" if salary_data.get("gross") else ""

    parts = []
    if s_from:
        parts.append(f"от {s_from:,}".replace(",", " "))
    if s_to:
        parts.append(f"до {s_to:,}".replace(",", " "))
    if parts:
        return f"{' '.join(parts)} {currency}{gross_str}"
    return "N/A"


def build_history_details_markdown(
    details: dict,
    record: dict,
    *,
    vacancy_id: str,
    html_converter,
) -> str:
    """Формирует markdown для панели деталей истории"""
    salary_line = _format_salary_line(details.get("salary"))
    desc_html = details.get("description", "")
    desc_md = html_converter.handle(html.unescape(desc_html)).strip()
    skills = details.get("key_skills") or []
    if skills:
        skills_text = "* " + "\n* ".join(skill["name"] for skill in skills)
    else:
        skills_text = "Не указаны"

    applied_label = format_datetime(record.get("applied_at"))
    status_label = record.get("status_display") or format_history_status(
        record.get("status"),
        record.get("reason"),
        record.get("applied_at"),
    )
    reason_label = ""
    if normalize_status_code(record.get("status")) == "failed":
        reason_code = normalize_reason_code(record.get("reason"))
        if reason_code in ERROR_REASON_LABELS:
            reason_label = ERROR_REASON_LABELS[reason_code]
        elif record.get("reason"):
            reason_label = str(record.get("reason"))
    sent_label = "да" if bool(record.get("was_delivered")) else "нет"

    company_name = (
        details.get("employer", {}).get("name")
        or record.get("employer_name")
        or "-"
    )
    link = details.get("alternate_url") or "—"

    doc = (
        f"## {details.get('name', record.get('vacancy_title', vacancy_id))}\n\n"
        f"**Компания:** {company_name}\n\n"
        f"**Ссылка:** {link}\n\n"
        f"**Зарплата:** {salary_line}\n\n"
        f"**Ключевые навыки:**\n{skills_text}\n\n"
        f"**Дата и время отклика:** {applied_label}\n\n"
        f"**Статус:** {status_label}\n\n"
        f"**✉:** {sent_label}\n\n"
    )
    if reason_label:
        doc += f"**Причина:** {reason_label}\n\n"
    doc += "**Описание:**\n\n"
    if desc_md:
        doc += f"{desc_md}\n"
    else:
        doc += "[dim]Описание вакансии недоступно.[/dim]\n"
    return doc


__all__ = ["build_history_details_markdown"]
