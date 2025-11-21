"""Экранные формы пользовательского интерфейса"""

from .config import ConfigScreen
from .history import NegotiationHistoryScreen
from .profile_select import ProfileSelectionScreen
from .search_mode import SearchModeScreen
from .vacancy_list import VacancyListScreen

__all__ = [
    "ConfigScreen",
    "NegotiationHistoryScreen",
    "ProfileSelectionScreen",
    "SearchModeScreen",
    "VacancyListScreen",
]
