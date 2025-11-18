"""Служебные модули для UI"""

from .apply_service import ApplyResult, apply_to_vacancies
from .dictionaries import cache_dictionaries
from .history_service import fetch_resume_history, load_delivery_summary
from .vacancy_service import deduplicate_vacancies, load_vacancies

__all__ = [
    "ApplyResult",
    "apply_to_vacancies",
    "cache_dictionaries",
    "deduplicate_vacancies",
    "fetch_resume_history",
    "load_delivery_summary",
    "load_vacancies",
]
