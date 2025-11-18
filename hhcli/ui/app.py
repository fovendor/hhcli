from __future__ import annotations

from typing import Optional

from textual.app import App
from textual.binding import Binding

from ..client import AuthorizationPending
from ..constants import ConfigKeys, LogSource
from ..database import (
    get_active_profile_name,
    get_all_profiles,
    get_default_config,
    load_profile_config,
    log_to_db,
    set_active_profile,
)
from .css_manager import CssManager
from .modules.dictionaries import cache_dictionaries as cache_dictionaries_service
from .screens.profile_select import ProfileSelectionScreen
from .screens.resume_select import ResumeSelectionScreen
from .screens.search_mode import SearchModeScreen

CSS_MANAGER = CssManager()


class HHCliApp(App):
    """Основное TUI-приложение hhcli"""

    CSS_PATH = CSS_MANAGER.css_file
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("q", "quit", "Выход", show=True, priority=True),
        Binding("й", "quit", "Выход (RU)", show=False, priority=True),
    ]

    def __init__(self, client) -> None:
        super().__init__(watch_css=True)
        self.client = client
        self.dictionaries = {}
        self.css_manager = CSS_MANAGER
        self.title = "hh-cli"

    def apply_theme_from_profile(self, profile_name: Optional[str] = None) -> None:
        """Применяет тему, указанную в конфигурации профиля"""
        theme_name: Optional[str] = None
        if profile_name:
            try:
                profile_config = load_profile_config(profile_name)
                theme_name = profile_config.get(ConfigKeys.THEME)
            except Exception as exc:  # pragma: no cover
                log_to_db(
                    "WARN",
                    LogSource.TUI,
                    f"Не удалось загрузить тему профиля '{profile_name}': {exc}",
                )
        if not theme_name:
            defaults = get_default_config()
            theme_name = defaults.get(ConfigKeys.THEME, "hhcli-base")
        try:
            self.css_manager.set_theme(theme_name or "hhcli-base")
        except ValueError:
            self.css_manager.set_theme("hhcli-base")

    async def on_mount(self) -> None:
        log_to_db("INFO", LogSource.TUI, "Приложение смонтировано")
        all_profiles = get_all_profiles()
        active_profile = get_active_profile_name()
        theme_profile = active_profile
        if not theme_profile and all_profiles:
            theme_profile = all_profiles[0]["profile_name"]
        self.apply_theme_from_profile(theme_profile)

        if not all_profiles:
            self.exit(
                "В базе не найдено ни одного профиля. "
                "Войдите через --auth <имя_профиля>."
            )
            return

        if len(all_profiles) == 1:
            profile_name = all_profiles[0]["profile_name"]
            log_to_db(
                "INFO", LogSource.TUI,
                f"Найден один профиль '{profile_name}', используется автоматически."
            )
            set_active_profile(profile_name)
            await self.proceed_with_profile(profile_name)
        else:
            log_to_db("INFO", LogSource.TUI, "Найдено несколько профилей — показ выбора.")
            self.push_screen(ProfileSelectionScreen(all_profiles), self.on_profile_selected)

    async def on_profile_selected(self, selected_profile: Optional[str]) -> None:
        if not selected_profile:
            log_to_db("INFO", LogSource.TUI, "Выбор профиля отменён, выходим.")
            self.exit()
            return
        log_to_db("INFO", LogSource.TUI, f"Выбран профиль '{selected_profile}' из списка.")
        await self.proceed_with_profile(selected_profile)

    async def proceed_with_profile(self, profile_name: str) -> None:
        try:
            self.client.load_profile_data(profile_name)
            self.sub_title = f"Профиль: {profile_name}"
            self.apply_theme_from_profile(profile_name)
            self.client.ensure_active_token()

            self.run_worker(self.cache_dictionaries, thread=True, name="DictCacheWorker")

            self.notify(
                "Синхронизация истории откликов...",
                title="Синхронизация",
                timeout=2,
            )
            self.run_worker(self._sync_history_worker, thread=True, name="SyncWorker")

            log_to_db("INFO", LogSource.TUI, f"Загрузка резюме для '{profile_name}'")
            resumes = self.client.get_my_resumes()
            items = (resumes or {}).get("items") or []
            if len(items) == 1:
                r = items[0]
                self.push_screen(
                    SearchModeScreen(
                        resume_id=r["id"],
                        resume_title=r["title"],
                        is_root_screen=True,
                    )
                )
            else:
                self.push_screen(ResumeSelectionScreen(resume_data=resumes))
        except AuthorizationPending as auth_exc:
            log_to_db(
                "WARN",
                LogSource.TUI,
                f"Профиль '{profile_name}' требует повторной авторизации: {auth_exc}",
            )
            self.sub_title = f"Профиль: {profile_name} (ожидание авторизации)"
            self.notify(
                "Требуется повторная авторизация. "
                "Завершите вход в открывшемся браузере и повторите выбор профиля.",
                title="Авторизация",
                severity="warning",
                timeout=6,
            )
            all_profiles = get_all_profiles()
            self.push_screen(ProfileSelectionScreen(all_profiles), self.on_profile_selected)
        except Exception as exc:
            log_to_db("ERROR", LogSource.TUI, f"Критическая ошибка профиля/резюме: {exc}")
            self.exit(result=exc)

    def _sync_history_worker(self) -> None:
        """Синхронизирует историю откликов и обрабатывает запрос повторной авторизации"""
        try:
            self.client.sync_negotiation_history()
        except AuthorizationPending as auth_exc:
            log_to_db(
                "WARN",
                LogSource.SYNC_ENGINE,
                f"Синхронизация истории остановлена: {auth_exc}",
            )
            self.call_from_thread(
                self.notify,
                "Авторизация требуется для синхронизации истории откликов.",
                title="Авторизация",
                severity="warning",
                timeout=4,
            )

    async def cache_dictionaries(self) -> None:
        """Загружает словари и обновляет справочные данные"""
        self.dictionaries = cache_dictionaries_service(self.client, notify=self.notify)

    def action_quit(self) -> None:
        log_to_db("INFO", LogSource.TUI, "Пользователь запросил выход.")
        self.css_manager.cleanup()
        self.exit()


__all__ = ["HHCliApp", "CSS_MANAGER"]
