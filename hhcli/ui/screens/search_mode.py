from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, OptionList, Static
from textual.widgets._option_list import Option

from ...constants import LogSource, SearchMode
from ...database import (
    clear_active_profile,
    delete_profile,
    get_all_profiles,
    load_profile_config,
    log_to_db,
)
from ..dialogs import CodeConfirmationDialog
from .config import ConfigScreen
from .profile_select import ProfileSelectionScreen
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
                                yield Button("Удалить профиль", id="search_mode_delete_btn", variant="error")
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
        if event.button.id == "search_mode_delete_btn":
            self._confirm_delete_profile()

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

    def _confirm_delete_profile(self) -> None:
        profile_name = self.app.client.profile_name or ""
        if not profile_name:
            self.app.notify("Нет активного профиля для удаления.", title="Профиль", severity="warning", timeout=4)
            return
        message = (
            f"Профиль [b]{profile_name}[/b] и все связанные данные (история откликов, кэш, настройки) "
            "будут безвозвратно удалены.\nВведите число: [b red]{code}[/b red] для подтверждения."
        )
        dialog = CodeConfirmationDialog(
            title="Удаление профиля",
            message=message,
            confirm_label="Удалить",
            confirm_variant="error",
        )
        self.app.push_screen(dialog, self._handle_profile_delete_result)

    def _handle_profile_delete_result(self, decision: str | None) -> None:
        if decision != "submit":
            self.query_one(OptionList).focus()
            return
        self.run_worker(self._delete_profile_worker(), thread=True, exclusive=True)

    async def _delete_profile_worker(self) -> None:
        profile_name = self.app.client.profile_name or ""
        if not profile_name:
            self.app.call_from_thread(
                self.app.notify,
                "Нет активного профиля для удаления.",
                title="Профиль",
                severity="warning",
                timeout=4,
            )
            return
        try:
            delete_profile(profile_name)
            clear_active_profile(profile_name)
            log_to_db("INFO", LogSource.SEARCH_MODE_SCREEN, f"Профиль '{profile_name}' удалён.")
            remaining = get_all_profiles()
            self.app.call_from_thread(self._after_profile_deleted, profile_name, remaining)
        except Exception as exc:  # pragma: no cover
            log_to_db("ERROR", LogSource.SEARCH_MODE_SCREEN, f"Не удалось удалить профиль '{profile_name}': {exc}")
            self.app.call_from_thread(
                self.app.notify,
                f"Не удалось удалить профиль: {exc}",
                title="Профиль",
                severity="error",
                timeout=4,
            )

    def _after_profile_deleted(self, profile_name: str, remaining_profiles: list[dict]) -> None:
        if self.app.client.profile_name == profile_name:
            self.app.client.profile_name = None
            self.app.client.access_token = None
        self.app.notify(
            f"Профиль '{profile_name}' удалён со всеми данными.",
            title="Профиль",
            severity="warning",
            timeout=5,
        )
        if self.app.screen is self:
            self.app.pop_screen()
        self.app.push_screen(ProfileSelectionScreen(remaining_profiles), self.app.on_profile_selected)


__all__ = ["SearchModeScreen"]
