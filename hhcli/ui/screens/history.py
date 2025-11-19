from __future__ import annotations

import html2text
from typing import Optional

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import (
    Footer,
    Header,
    LoadingIndicator,
    Markdown,
    Static,
    TabPane,
    TabbedContent,
    TextArea,
)
from textual.widgets._option_list import Option, OptionList
from textual.widgets.text_area import TextAreaTheme

from ...client import AuthorizationPending
from ...constants import ConfigKeys, LogSource
from ...database import (
    get_default_config,
    get_vacancy_from_cache,
    load_profile_config,
    log_to_db,
    save_vacancy_to_cache,
)
from ..modules.history_service import fetch_resume_history
from ..utils.constants import MAX_COLUMN_WIDTH
from ..utils.formatting import (
    clamp,
    format_date,
    format_datetime,
    format_segment,
    normalize_width_map,
    set_loader_visible,
)
from ..widgets import HistoryOptionList
from ..widgets.history_panel import build_history_details_markdown
from .config import ConfigScreen


class NegotiationHistoryScreen(Screen):
    """Экран просмотра истории откликов"""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Назад"),
        Binding("c", "edit_config", "Настройки", show=True),
        Binding("с", "edit_config", "Настройки (RU)", show=False),
    ]

    COLUMN_KEYS = ["index", "title", "company", "status", "sent", "date"]

    def __init__(self, resume_id: str, resume_title: str | None = None) -> None:
        super().__init__()
        self.resume_id = str(resume_id or "")
        self.resume_title = (resume_title or "").strip()
        self.history: list[dict] = []
        self.history_by_vacancy: dict[str, dict] = {}
        self._pending_details_id: Optional[str] = None
        self._debounce_timer: Optional[Timer] = None

        self.html_converter = html2text.HTML2Text()
        self.html_converter.body_width = 0
        self.html_converter.ignore_links = False
        self.html_converter.ignore_images = True
        self.html_converter.mark_code = True
        self._quit_binding_q = None
        self._quit_binding_cyrillic = None

    def compose(self) -> ComposeResult:
        with Vertical(id="history_screen"):
            yield Header(show_clock=True, name="hh-cli")
            if self.resume_title:
                yield Static(
                    f"Резюме: [b cyan]{self.resume_title}[/b cyan]\n",
                    id="history_resume_label",
                )
            with Horizontal(id="history_layout"):
                with Vertical(id="history_panel", classes="pane") as history_panel:
                    history_panel.border_title = "История откликов"
                    history_panel.styles.border_title_align = "left"
                    yield Static(id="history_list_header")
                    yield HistoryOptionList(id="history_list")
                with Vertical(id="history_details_panel", classes="pane") as details_panel:
                    details_panel.border_title = "Детали и переписка"
                    details_panel.styles.border_title_align = "left"
                    with TabbedContent(initial="history_description_tab", id="history_details_tabs"):
                        with TabPane("Описание вакансии", id="history_description_tab"):
                            with VerticalScroll(id="history_details_pane"):
                                yield Markdown(
                                    "[dim]Выберите отклик слева, чтобы увидеть детали.[/dim]",
                                    id="history_details",
                                )
                                yield LoadingIndicator(id="history_loader")
                        with TabPane("Переписка", id="history_chat_tab"):
                            with Vertical(id="history_chat_split"):
                                with VerticalScroll(id="history_chat_upper"):
                                    yield Static(
                                        "[dim]Здесь будет информация о переписке.[/dim]",
                                        id="history_chat_placeholder_top",
                                    )
                                with VerticalScroll(id="history_chat_lower"):
                                    chat_input = TextArea(id="history_chat_input")
                                    chat_input.placeholder = "Введите сообщение..."
                                    chat_input.show_line_numbers = False
                                    self._apply_history_chat_text_area_theme(chat_input)
                                    yield chat_input
            yield Footer()

    def on_mount(self) -> None:
        bindings_map = self.app._bindings
        self._quit_binding_q = bindings_map.key_to_bindings.pop("q", None)
        self._quit_binding_cyrillic = bindings_map.key_to_bindings.pop("й", None)
        self._reload_history_layout_preferences()
        self._apply_history_workspace_widths()
        self._update_history_header()
        self._refresh_history()
        self._apply_history_chat_text_area_theme()

    def on_screen_resume(self) -> None:
        self.app.apply_theme_from_profile(self.app.client.profile_name)
        self._reload_history_layout_preferences()
        self._apply_history_workspace_widths()
        self._update_history_header()
        self._apply_history_chat_text_area_theme()
        self.query_one(HistoryOptionList).focus()

    def on_unmount(self) -> None:
        bindings_map = self.app._bindings
        if self._quit_binding_q:
            bindings_map.key_to_bindings["q"] = self._quit_binding_q
        if self._quit_binding_cyrillic:
            bindings_map.key_to_bindings["й"] = self._quit_binding_cyrillic

    def _reload_history_layout_preferences(self) -> None:
        config = load_profile_config(self.app.client.profile_name)
        defaults = get_default_config()
        self._history_left_percent = clamp(
            int(
                config.get(
                    ConfigKeys.HISTORY_LEFT_PANE_PERCENT,
                    defaults[ConfigKeys.HISTORY_LEFT_PANE_PERCENT],
                )
            ),
            10,
            90,
        )
        history_width_values = {
            "index": clamp(
                int(
                    config.get(
                        ConfigKeys.HISTORY_COL_INDEX_WIDTH,
                        defaults[ConfigKeys.HISTORY_COL_INDEX_WIDTH],
                    )
                ),
                1,
                MAX_COLUMN_WIDTH,
            ),
            "title": clamp(
                int(
                    config.get(
                        ConfigKeys.HISTORY_COL_TITLE_WIDTH,
                        defaults[ConfigKeys.HISTORY_COL_TITLE_WIDTH],
                    )
                ),
                1,
                MAX_COLUMN_WIDTH,
            ),
            "company": clamp(
                int(
                    config.get(
                        ConfigKeys.HISTORY_COL_COMPANY_WIDTH,
                        defaults[ConfigKeys.HISTORY_COL_COMPANY_WIDTH],
                    )
                ),
                1,
                MAX_COLUMN_WIDTH,
            ),
            "status": clamp(
                int(
                    config.get(
                        ConfigKeys.HISTORY_COL_STATUS_WIDTH,
                        defaults[ConfigKeys.HISTORY_COL_STATUS_WIDTH],
                    )
                ),
                1,
                MAX_COLUMN_WIDTH,
            ),
            "sent": clamp(
                int(
                    config.get(
                        ConfigKeys.HISTORY_COL_SENT_WIDTH,
                        defaults[ConfigKeys.HISTORY_COL_SENT_WIDTH],
                    )
                ),
                1,
                MAX_COLUMN_WIDTH,
            ),
            "date": clamp(
                int(
                    config.get(
                        ConfigKeys.HISTORY_COL_DATE_WIDTH,
                        defaults[ConfigKeys.HISTORY_COL_DATE_WIDTH],
                    )
                ),
                1,
                MAX_COLUMN_WIDTH,
            ),
        }
        self._history_column_widths = normalize_width_map(
            history_width_values, self.COLUMN_KEYS, max_value=MAX_COLUMN_WIDTH
        )

    def _apply_history_workspace_widths(self) -> None:
        try:
            history_panel = self.query_one("#history_panel")
            details_panel = self.query_one("#history_details_panel")
        except Exception:
            return
        history_panel.styles.width = f"{self._history_left_percent}%"
        details_panel.styles.width = f"{max(5, 100 - self._history_left_percent)}%"

    def _update_history_header(self) -> None:
        try:
            header = self.query_one("#history_list_header", Static)
        except Exception:
            return
        header.update(self._build_header_text())

    def _refresh_history(self) -> None:
        self._reload_history_layout_preferences()
        self._apply_history_workspace_widths()
        header = self.query_one("#history_list_header", Static)
        header.update(self._build_header_text())

        option_list = self.query_one(HistoryOptionList)
        option_list.clear_options()

        profile_name = self.app.client.profile_name
        entries = fetch_resume_history(profile_name, self.resume_id)

        self.history = entries
        self.history_by_vacancy = {
            str(item.get("vacancy_id")): item for item in entries if item.get("vacancy_id")
        }

        if not entries:
            option_list.add_option(
                Option("История откликов пуста.", "__none__", disabled=True)
            )
            self.query_one("#history_details", Markdown).update(
                "[dim]Нет данных для отображения.[/dim]"
            )
            set_loader_visible(self, "history_loader", False)
            return

        for idx, entry in enumerate(entries, start=1):
            vacancy_id = str(entry.get("vacancy_id") or "")
            title = entry.get("vacancy_title") or vacancy_id
            company = entry.get("employer_name") or "-"
            applied_label = format_date(entry.get("applied_at"))
            status_label = entry.get("status_display") or "-"
            sent_label = entry.get("sent_display") or (
                "да" if entry.get("was_delivered") else "нет"
            )

            row_text = self._build_row_text(
                index=f"#{idx}",
                title=title,
                company=company,
                status=status_label,
                delivered=sent_label,
                applied=applied_label,
            )
            option_list.add_option(Option(row_text, vacancy_id))

        option_list.highlighted = 0 if option_list.option_count else None
        option_list.focus()

        if option_list.option_count and option_list.highlighted is not None:
            focused_option = option_list.get_option_at_index(option_list.highlighted)
            if focused_option and focused_option.id not in (None, "__none__"):
                self.load_vacancy_details(str(focused_option.id))

    def _build_header_text(self) -> Text:
        widths = self._history_column_widths
        return Text.assemble(
            format_segment("№", widths["index"], style="bold"),
            Text("  "),
            format_segment("Название вакансии", widths["title"], style="bold"),
            Text("  "),
            format_segment("Компания", widths["company"], style="bold"),
            Text("  "),
            format_segment("Статус", widths["status"], style="bold"),
            Text("  "),
            format_segment("✉", widths["sent"], style="bold"),
            Text("  "),
            format_segment("Дата отклика", widths["date"], style="bold"),
        )

    def _build_row_text(
        self,
        *,
        index: str,
        title: str,
        company: str,
        status: str,
        delivered: str,
        applied: str,
    ) -> Text:
        widths = self._history_column_widths
        return Text.assemble(
            format_segment(index, widths["index"], style="bold"),
            Text("  "),
            format_segment(title, widths["title"]),
            Text("  "),
            format_segment(company, widths["company"]),
            Text("  "),
            format_segment(status, widths["status"]),
            Text("  "),
            format_segment(delivered, widths["sent"]),
            Text("  "),
            format_segment(applied, widths["date"]),
        )

    @staticmethod
    def _format_datetime(value):
        return format_datetime(value)

    @staticmethod
    def _format_date(value):
        return format_date(value)

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if self._debounce_timer:
            self._debounce_timer.stop()
        vacancy_id = event.option.id
        if not vacancy_id or vacancy_id == "__none__":
            return
        self._debounce_timer = self.set_timer(
            0.2, lambda vid=str(vacancy_id): self.load_vacancy_details(vid)
        )

    def load_vacancy_details(self, vacancy_id: Optional[str]) -> None:
        if not vacancy_id:
            return
        self._pending_details_id = vacancy_id
        set_loader_visible(self, "history_loader", True)
        self.query_one("#history_details", Markdown).update("")

        cached = get_vacancy_from_cache(vacancy_id)
        if cached:
            self.display_history_details(cached, vacancy_id)
            set_loader_visible(self, "history_loader", False)
            return

        self.run_worker(
            self.fetch_history_details(vacancy_id),
            exclusive=True,
            thread=True,
        )

    def _build_history_chat_theme(self) -> TextAreaTheme:
        css_theme = getattr(self.app, "css_manager", None)
        theme = getattr(css_theme, "theme", None)
        colors = getattr(theme, "colors", {}) if theme else {}
        background = colors.get("background2", "#3B4252")
        text_color = colors.get("foreground3", "#ECEFF4")
        theme_name = getattr(theme, "_name", "default")
        return TextAreaTheme(
            name=f"history-chat-{theme_name}",
            base_style=Style(color=text_color, bgcolor=background),
            cursor_line_style=None,
            cursor_line_gutter_style=None,
        )

    def _apply_history_chat_text_area_theme(self, text_area: TextArea | None = None) -> None:
        target = text_area or self._get_history_chat_text_area()
        if target is None:
            return
        chat_theme = self._build_history_chat_theme()
        target.register_theme(chat_theme)
        target.theme = chat_theme.name

    def _get_history_chat_text_area(self) -> TextArea | None:
        try:
            return self.query_one("#history_chat_input", TextArea)
        except Exception:
            return None

    async def fetch_history_details(self, vacancy_id: str) -> None:
        try:
            details = self.app.client.get_vacancy_details(vacancy_id)
            save_vacancy_to_cache(vacancy_id, details)
            self.app.call_from_thread(
                self.display_history_details,
                details,
                vacancy_id,
            )
        except AuthorizationPending as auth_exc:
            log_to_db(
                "WARN",
                LogSource.VACANCY_LIST_SCREEN,
                f"Загрузка деталей отклика приостановлена: {auth_exc}",
            )
            self.app.call_from_thread(
                self.app.notify,
                "Авторизуйтесь повторно, чтобы просмотреть детали отклика.",
                title="Авторизация",
                severity="warning",
                timeout=4,
            )
            self.app.call_from_thread(
                self._display_details_error,
                "Требуется авторизация для просмотра деталей.",
            )
        except Exception as exc:  # pragma: no cover - сетевые ошибки
            log_to_db(
                "ERROR",
                LogSource.VACANCY_LIST_SCREEN,
                f"Ошибка деталей {vacancy_id}: {exc}",
            )
            self.app.call_from_thread(
                self._display_details_error, f"Ошибка загрузки: {exc}"
            )

    def display_history_details(self, details: dict, vacancy_id: str) -> None:
        if self._pending_details_id != vacancy_id:
            return

        record = self.history_by_vacancy.get(vacancy_id, {})
        doc = build_history_details_markdown(
            details,
            record,
            vacancy_id=vacancy_id,
            html_converter=self.html_converter,
        )
        self.query_one("#history_details").update(doc)
        set_loader_visible(self, "history_loader", False)
        self.query_one("#history_details_pane").scroll_home(animate=False)

    def action_edit_config(self) -> None:
        self.app.push_screen(ConfigScreen(), self._on_config_closed)

    def _on_config_closed(self, _: bool | None) -> None:
        self.query_one(HistoryOptionList).focus()

    def _display_details_error(self, message: str) -> None:
        self.query_one("#history_details", Markdown).update(message)
        set_loader_visible(self, "history_loader", False)


__all__ = ["NegotiationHistoryScreen"]
