from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, OptionList, Static
from textual.widgets._option_list import Option

from ...constants import LogSource
from ...database import log_to_db, set_active_profile, get_all_profiles
from ..dialogs import ProfileCreateDialog


class ProfileSelectionScreen(Screen):
    """Экран выбора профиля или создания нового при первом запуске."""

    BINDINGS = [
        Binding("n", "show_new_profile", "Новый профиль", show=True),
        Binding("escape", "cancel", "Отмена", show=False),
        Binding("й", "cancel", "Отмена (RU)", show=False),
    ]

    def __init__(self, all_profiles: list[dict] | None = None) -> None:
        super().__init__()
        self.all_profiles = all_profiles or []

    def compose(self) -> ComposeResult:
        with Vertical(id="profile_screen"):
            with Center():
                with Vertical(id="profile_wrapper"):
                    with Vertical(id="profile_panel", classes="pane center-panel") as profile_panel:
                        profile_panel.border_title = "Профили"
                        profile_panel.styles.border_title_align = "left"
                        with Vertical(id="profile_content"):
                            yield OptionList(id="profile_list")
                            with Vertical(id="profile_actions"):
                                yield Button("Создать новый профиль", id="profile_create_btn", variant="primary")
            yield Footer()

    def on_mount(self) -> None:
        self._populate_profiles()
        if self.all_profiles:
            self.query_one(OptionList).focus()
        else:
            self.action_show_new_profile()

    def _populate_profiles(self) -> None:
        profiles = self.all_profiles or get_all_profiles()
        self.all_profiles = profiles
        option_list = self.query_one(OptionList)
        option_list.clear_options()
        if not profiles:
            option_list.add_option(Option("Профилей пока нет.", "__none__", disabled=True))
            option_list.display = False
            return
        option_list.display = True
        for p in profiles:
            name = p.get("profile_name") or "Без имени"
            email = p.get("email") or "-"
            option_list.add_option(Option(f"{name} — {email}", name))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option.id
        self._select_profile(str(option_id)) if option_id not in (None, "__none__") else None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "profile_create_btn":
            self.action_show_new_profile()
        elif event.button.id and event.button.id.startswith("profile_select_"):
            self._select_profile(event.button.id.replace("profile_select_", "", 1))

    def action_show_new_profile(self) -> None:
        self.app.push_screen(ProfileCreateDialog(), self._handle_profile_create_result)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _handle_profile_create_result(self, name: str | None) -> None:
        if name:
            self._start_profile_creation(name.strip())
        else:
            if self.all_profiles:
                self.query_one(OptionList).focus()

    def _start_profile_creation(self, name: str) -> None:
        normalized = name.strip()
        if not normalized:
            self.app.notify("Введите имя профиля.", title="Профиль", severity="warning")
            return
        if any((p.get("profile_name") or "") == normalized for p in self.all_profiles):
            self.app.notify("Такое имя профиля уже существует.", title="Профиль", severity="warning")
            return
        self.app.notify(f"Запуск авторизации для профиля {normalized}...", title="Профиль")
        self.run_worker(self._create_profile_worker(normalized), thread=False, exclusive=True)

    async def _create_profile_worker(self, profile_name: str):
        try:
            success = self.app.client.authorize(profile_name)
            if success:
                set_active_profile(profile_name)
                log_to_db("INFO", LogSource.PROFILE_SCREEN, f"Профиль '{profile_name}' создан.")
                self.dismiss(profile_name)
            else:
                self.app.notify(
                    "Авторизация не завершена.",
                    title="Профиль",
                    severity="error",
                    timeout=4,
                )
        except Exception as exc:  # pragma: no cover
            log_to_db("ERROR", LogSource.PROFILE_SCREEN, f"Ошибка создания профиля: {exc}")
            self.app.notify(
                f"Не удалось создать профиль: {exc}",
                title="Профиль",
                severity="error",
                timeout=6,
            )

    def _select_profile(self, profile_name: str) -> None:
        if not profile_name or profile_name == "__none__":
            return
        log_to_db("INFO", LogSource.PROFILE_SCREEN, f"Выбран профиль '{profile_name}'")
        set_active_profile(profile_name)
        self.dismiss(profile_name)


__all__ = ["ProfileSelectionScreen"]
