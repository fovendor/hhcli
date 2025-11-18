from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ...client import AuthorizationPending
from ...constants import ApiErrorReason, ERROR_REASON_LABELS, LogSource
from ...database import log_to_db, record_apply_action


@dataclass(slots=True)
class ApplyResult:
    vacancy_id: str
    title: str
    employer: str | None
    ok: bool
    reason_code: str | None
    human_reason: str | None


def apply_to_vacancies(
    *,
    client,
    profile_name: str,
    resume_id: str,
    resume_title: str,
    vacancy_ids: Iterable[str],
    vacancies_by_id: dict[str, dict],
    cover_letter: str,
) -> list[ApplyResult]:
    """Отправляет отклики и возвращает подробные результаты"""
    results: list[ApplyResult] = []
    for vacancy_id in vacancy_ids:
        vacancy = vacancies_by_id.get(vacancy_id, {})
        vac_title = vacancy.get("name", vacancy_id)
        employer = (vacancy.get("employer") or {}).get("name")
        try:
            ok, reason_code = client.apply_to_vacancy(
                resume_id=resume_id,
                vacancy_id=vacancy_id,
                message=cover_letter,
            )
        except AuthorizationPending as auth_exc:
            log_to_db(
                "WARN",
                LogSource.VACANCY_LIST_SCREEN,
                f"Отправка откликов остановлена: {auth_exc}",
            )
            raise

        if ok:
            record_apply_action(
                vacancy_id,
                profile_name,
                resume_id,
                resume_title,
                vac_title,
                employer,
                ApiErrorReason.APPLIED,
                None,
            )
        else:
            record_apply_action(
                vacancy_id,
                profile_name,
                resume_id,
                resume_title,
                vac_title,
                employer,
                "failed",
                reason_code,
            )

        human_reason = ERROR_REASON_LABELS.get(reason_code, reason_code)
        results.append(
            ApplyResult(
                vacancy_id=vacancy_id,
                title=vac_title,
                employer=employer,
                ok=ok,
                reason_code=reason_code,
                human_reason=human_reason,
            )
        )
    return results


__all__ = ["ApplyResult", "apply_to_vacancies"]
