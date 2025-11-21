from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, OptionList, Static
from textual.widgets._option_list import Option

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
        with Vertical(id="search_mode_screen"):
            with Center():
                with Vertical(id="search_mode_wrapper"):
                    with Vertical(id="search_mode_panel", classes="pane center-panel") as search_panel:
                        search_panel.border_title = f"Режим поиска: {self.resume_title}"
                        search_panel.styles.border_title_align = "left"
                        with Vertical(id="search_mode_content"):
                            yield OptionList(id="search_mode_list")
                            with Vertical(id="search_mode_actions"):
                                yield Button("Открыть настройки", id="search_mode_config_btn", variant="primary")
            yield Footer()

    def action_handle_escape(self) -> None:
        if self.is_root_screen:
            self.app.exit()
        else:
            self.app.pop_screen()

    def on_mount(self) -> None:
        self._populate_modes()
        self.query_one(OptionList).focus()

    def action_edit_config(self) -> None:
        """Открывает экран редактирования конфигурации"""
        self.app.push_screen(ConfigScreen())

    def on_screen_resume(self) -> None:
        self.app.apply_theme_from_profile(self.app.client.profile_name)
        self.query_one(OptionList).focus()

    def _populate_modes(self) -> None:
        option_list = self.query_one(OptionList)
        option_list.clear_options()
        option_list.add_option(Option("Автоматический — рекомендации hh.ru", SearchMode.AUTO.value))
        option_list.add_option(Option("Ручной — поиск по ключевым словам", SearchMode.MANUAL.value))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option.id
        if option_id:
            self.action_run_search(str(option_id))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "search_mode_config_btn":
            self.action_edit_config()

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
