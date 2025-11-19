from __future__ import annotations

from typing import Iterable

from ...constants import SearchMode
from ...database import load_profile_config
from ..utils.formatting import normalize


def load_vacancies(
    client,
    *,
    resume_id: str,
    search_mode: SearchMode,
    config_snapshot: dict | None,
    page: int,
    per_page: int,
) -> tuple[list[dict], int, dict]:
    """Выполняет запрос вакансий и возвращает элементы, количество страниц и актуальный snapshot"""
    snapshot = dict(config_snapshot or {})
    if search_mode == SearchMode.MANUAL:
        snapshot = load_profile_config(client.profile_name)

    if search_mode == SearchMode.AUTO:
        result = client.get_similar_vacancies(resume_id, page=page, per_page=per_page)
    else:
        result = client.search_vacancies(snapshot, page=page, per_page=per_page)

    items = (result or {}).get("items", [])
    pages = (result or {}).get("pages", 1)
    return items, pages, snapshot


def deduplicate_vacancies(
    vacancies: Iterable[dict],
    *,
    enabled: bool,
) -> tuple[list[dict], int]:
    """Удаляет дубли вакансий по названию и компании"""
    vac_list = list(vacancies)
    if not enabled:
        return vac_list, 0

    seen_keys = set()
    unique_vacancies: list[dict] = []
    for vac in vac_list:
        name = normalize(vac.get("name"))
        employer = vac.get("employer") or {}
        emp_key = normalize(employer.get("id") or employer.get("name"))
        key = f"{name}|{emp_key}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique_vacancies.append(vac)

    removed = len(vac_list) - len(unique_vacancies)
    return unique_vacancies, removed


__all__ = ["deduplicate_vacancies", "load_vacancies"]
