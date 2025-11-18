from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from ...constants import LogSource, SearchMode
from ...database import load_profile_config, log_to_db
from .config import ConfigScreen
from .vacancy_list import VacancyListScreen


class SearchModeScreen(Screen):
    """Экран выбора режима поиска — автоматического или ручного"""

    BINDINGS = [
        Binding("1", "run_search('auto')", "Авто", show=False),
        Binding("2", "run_search('manual')", "Ручной", show=False),
        Binding("c", "edit_config", "Настройки", show=True),
        Binding("с", "edit_config", "Настройки (RU)", show=False),
        Binding("escape", "handle_escape", "Назад/Выход", show=True),
    ]

    def __init__(self, resume_id: str, resume_title: str, is_root_screen: bool = False) -> None:
        super().__init__()
        self.resume_id = resume_id
        self.resume_title = resume_title
        self.is_root_screen = is_root_screen

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, name="hh-cli")
        yield Static(f"Выбрано резюме: [b cyan]{self.resume_title}[/b cyan]\n")
        yield Static("[b]Выберите способ поиска вакансий:[/b]")
        yield Static("  [yellow]1)[/] Автоматический (рекомендации hh.ru)")
        yield Static("  [yellow]2)[/] Ручной (поиск по ключевым словам)")
        yield Footer()

    def action_handle_escape(self) -> None:
        if self.is_root_screen:
            self.app.exit()
        else:
            self.app.pop_screen()

    def action_edit_config(self) -> None:
        """Открывает экран редактирования конфигурации"""
        self.app.push_screen(ConfigScreen())

    def on_screen_resume(self) -> None:
        self.app.apply_theme_from_profile(self.app.client.profile_name)

    def action_run_search(self, mode: str) -> None:
        log_to_db("INFO", LogSource.SEARCH_MODE_SCREEN, f"Выбран режим '{mode}'")
        search_mode_enum = SearchMode(mode)

        if search_mode_enum == SearchMode.AUTO:
            self.app.push_screen(
                VacancyListScreen(
                    resume_id=self.resume_id,
                    search_mode=SearchMode.AUTO,
                    resume_title=self.resume_title,
                )
            )
        else:
            cfg = load_profile_config(self.app.client.profile_name)
            self.app.push_screen(
                VacancyListScreen(
                    resume_id=self.resume_id,
                    search_mode=SearchMode.MANUAL,
                    config_snapshot=cfg,
                    resume_title=self.resume_title,
                )
            )


__all__ = ["SearchModeScreen"]
