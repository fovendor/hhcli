from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll, Horizontal, Center
from textual.screen import Screen, ModalScreen
from textual.timer import Timer
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Static,
    Switch,
    TextArea,
    Select,
    SelectionList,
)
from textual.widgets._selection_list import Selection

from ...client import AuthorizationPending
from ...database import (
    list_areas,
    list_professional_roles,
    load_profile_config,
    log_to_db,
    save_profile_config,
    get_default_config,
)
from ...reference_data import ensure_reference_data
from ...constants import ConfigKeys, LogSource

COLUMN_WIDTH_MAX = 200


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(str(text).lower().split())


def _select_value(widget: Select) -> str | None:
    """Возвращает значение виджета Select и приводит пустое значение к None"""
    value = widget.value
    if value is None or value is Select.BLANK:
        return None
    return value


def _set_select_value(widget: Select, value: str | None) -> None:
    """Восстанавливает значение Select и очищает поле, если данных нет"""
    if value and value in getattr(widget, "_legal_values", set()):
        widget.value = value
    else:
        widget.clear()


def _theme_value(value: str | object | None) -> str | None:
    if value is None or value is Select.BLANK:
        return None
    return str(value)


@dataclass
class AreaOption:
    id: str
    label: str
    search_text: str


@dataclass
class RoleOption:
    id: str
    label: str
    search_text: str




TIMER_GLYPHS: dict[str, list[str]] = {
    " ": [
        "            ",
        "            ",
        "            ",
        "            ",
        "            ",
        "            ",
        "            ",
    ],
    "-": [
        "                  ",
        "                  ",
        "                  ",
        "██████████████████",
        "██████████████████",
        "                  ",
        "                  ",
    ],
    "0": [
        "██████████████████",
        "██              ██",
        "██              ██",
        "██              ██",
        "██              ██",
        "██              ██",
        "██████████████████",
    ],
    "1": [
        "                ██",
        "                ██",
        "                ██",
        "                ██",
        "                ██",
        "                ██",
        "                ██",
    ],
    "2": [
        "██████████████████",
        "                ██",
        "                ██",
        "██████████████████",
        "██                ",
        "██                ",
        "██████████████████",
    ],
    "3": [
        "██████████████████",
        "                ██",
        "                ██",
        "██████████████████",
        "                ██",
        "                ██",
        "██████████████████",
    ],
    "4": [
        "██              ██",
        "██              ██",
        "██              ██",
        "██████████████████",
        "                ██",
        "                ██",
        "                ██",
    ],
    "5": [
        "██████████████████",
        "██                ",
        "██                ",
        "██████████████████",
        "                ██",
        "                ██",
        "██████████████████",
    ],
    "6": [
        "██████████████████",
        "██                ",
        "██                ",
        "██████████████████",
        "██              ██",
        "██              ██",
        "██████████████████",
    ],
    "7": [
        "██████████████████",
        "                ██",
        "                ██",
        "                ██",
        "                ██",
        "                ██",
        "                ██",
    ],
    "8": [
        "██████████████████",
        "██              ██",
        "██              ██",
        "██████████████████",
        "██              ██",
        "██              ██",
        "██████████████████",
    ],
    "9": [
        "██████████████████",
        "██              ██",
        "██              ██",
        "██████████████████",
        "                ██",
        "                ██",
        "██████████████████",
    ],
    ":": [
        "          ",
        "    ██    ",
        "          ",
        "          ",
        "    ██    ",
        "          ",
        "          ",
    ],
}


@dataclass(frozen=True)
class LayoutField:
    label: str
    input_id: str
    config_key: str
    min_value: int = 1
    max_value: int = 100

    @property
    def selector(self) -> str:
        return f"#{self.input_id}"


@dataclass(frozen=True)
class LayoutSectionDef:
    title: str
    fields: tuple[LayoutField, ...]
    css_class: str


class AreaPickerDialog(ModalScreen[str | None]):
    """Диалог выбора региона или города"""

    BINDINGS = [
        Binding("escape", "cancel", "Отмена"),
        Binding("enter", "apply", "Применить"),
    ]

    def __init__(self, options: list[AreaOption], selected: str | None) -> None:
        super().__init__()
        self.options = options
        self.selected_id = selected
        self._filtered: list[AreaOption] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="picker"):
            yield Static("Выберите регион", classes="picker__title")
            yield Input(placeholder="Начните вводить название...", id="picker-search")
            yield SelectionList(id="picker-list")
            yield Static("[dim]Пробел — выбрать, Enter — применить[/dim]", classes="picker__hint")
            with Horizontal(classes="picker__buttons"):
                yield Button("Применить", id="picker-apply", variant="primary")
                yield Button("Очистить", id="picker-clear", variant="warning")
                yield Button("Отмена", id="picker-cancel")

    def on_mount(self) -> None:
        self._search = self.query_one("#picker-search", Input)
        self._list = self.query_one("#picker-list", SelectionList)
        self._refresh("")
        self.set_timer(0, lambda: self._search.focus())

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "picker-search":
            self._refresh(event.value)

    def on_selection_list_option_selected(
        self, event: SelectionList.OptionSelected
    ) -> None:
        event.stop()
        if event.selection_list.id == "picker-list":
            value = str(event.option.value)
            self.selected_id = None if self.selected_id == value else value
            self._refresh(self._search.value)

    def on_selection_list_selection_toggled(
        self, event: SelectionList.SelectionToggled
    ) -> None:
        if event.selection_list.id != "picker-list":
            return
        value = str(event.selection.value)
        selected_values = {str(val) for val in event.selection_list.selected}
        self.selected_id = value if value in selected_values else None
        self._refresh(self._search.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "picker-apply":
            self.dismiss(self.selected_id)
        elif event.button.id == "picker-clear":
            self.selected_id = None
            self._refresh(self._search.value)
        elif event.button.id == "picker-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_apply(self) -> None:
        self.dismiss(self.selected_id)

    def _refresh(self, query: str) -> None:
        normalized = _normalize(query)
        if normalized:
            candidates = [
                option
                for option in self.options
                if normalized in option.search_text
            ][:200]
        else:
            candidates = self.options[:200]
        self._filtered = candidates
        self._list.deselect_all()
        self._list.clear_options()
        for option in candidates:
            self._list.add_option(
                Selection(
                    f"{option.label} [dim]({option.id})[/]",
                    option.id,
                    initial_state=(option.id == self.selected_id),
                )
            )
        if self._list.option_count:
            self._list.highlighted = 0


class RolePickerDialog(ModalScreen[list[str] | None]):
    """Диалог выбора профессиональных ролей"""

    BINDINGS = [
        Binding("escape", "cancel", "Отмена"),
        Binding("enter", "apply", "Применить"),
    ]

    def __init__(self, options: list[RoleOption], selected: list[str]) -> None:
        super().__init__()
        self.options = options
        self.selected_ids = set(selected)
        self._filtered: list[RoleOption] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="picker"):
            yield Static("Выберите профессиональные роли", classes="picker__title")
            yield Input(placeholder="Поиск по названию или категории...", id="picker-search")
            yield SelectionList(id="picker-list")
            yield Static("[dim]Пробел — выбрать/снять, Enter — подтвердить[/dim]", classes="picker__hint")
            with Horizontal(classes="picker__buttons"):
                yield Button("Применить", id="picker-apply", variant="primary")
                yield Button("Очистить", id="picker-clear", variant="warning")
                yield Button("Отмена", id="picker-cancel")

    def on_mount(self) -> None:
        self._search = self.query_one("#picker-search", Input)
        self._list = self.query_one("#picker-list", SelectionList)
        self._refresh("")
        self.set_timer(0, lambda: self._search.focus())

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "picker-search":
            self._refresh(event.value)

    def on_selection_list_selection_toggled(
        self, event: SelectionList.SelectionToggled
    ) -> None:
        if event.selection_list.id != "picker-list":
            return
        self._toggle_value(str(event.selection.value))

    def on_selection_list_option_selected(
        self, event: SelectionList.OptionSelected
    ) -> None:
        event.stop()
        if event.selection_list.id == "picker-list":
            self._toggle_value(str(event.option.value))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "picker-apply":
            self.dismiss(sorted(self.selected_ids))
        elif event.button.id == "picker-clear":
            self.selected_ids.clear()
            self._refresh(self._search.value)
        elif event.button.id == "picker-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_apply(self) -> None:
        self.dismiss(sorted(self.selected_ids))

    def _refresh(self, query: str) -> None:
        normalized = _normalize(query)
        if normalized:
            candidates = [
                option
                for option in self.options
                if normalized in option.search_text
            ][:400]
        else:
            candidates = self.options[:400]
        self._filtered = candidates
        self._list.clear_options()
        for option in candidates:
            self._list.add_option(
                Selection(
                    option.label,
                    option.id,
                    initial_state=(option.id in self.selected_ids),
                )
            )
        if self._list.option_count:
            self._list.highlighted = 0

    def _toggle_value(self, value: str) -> None:
        if value in self.selected_ids:
            self.selected_ids.remove(value)
        else:
            self.selected_ids.add(value)


class ConfigUnsavedChangesDialog(ModalScreen[str | None]):
    """Диалог подтверждения выхода при несохранённых изменениях"""

    BINDINGS = [
        Binding("escape", "cancel", "Отмена"),
    ]

    def compose(self) -> ComposeResult:
        with Center(id="config-confirm-center"):
            with Vertical(id="config-confirm-dialog", classes="config-confirm") as dialog:
                dialog.border_title = "Подтверждение"
                dialog.styles.border_title_align = "left"
                yield Static(
                    "Сохранить внесённые изменения перед выходом?",
                    classes="config-confirm__message",
                    expand=True,
                )
                with Horizontal(classes="config-confirm__buttons"):
                    yield Button("Да", id="confirm-save", variant="success")
                    yield Button("Нет", id="confirm-discard", classes="decline")
                    yield Button("Отмена", id="confirm-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        mapping = {
            "confirm-save": "save",
            "confirm-discard": "discard",
            "confirm-cancel": "cancel",
        }
        decision = mapping.get(event.button.id or "")
        if decision:
            self.dismiss(decision)

    def action_cancel(self) -> None:
        self.dismiss("cancel")


class ConfigScreen(Screen):
    """Экран редактирования конфигурации профиля"""

    BINDINGS = [
        Binding("escape", "cancel", "Назад"),
        Binding("ctrl+s", "save_config", "Сохранить"),
    ]

    def __init__(self, resume_id: str | None = None, resume_title: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.resume_id = resume_id
        self.resume_title = resume_title
        self._raise_timer: Timer | None = None
        self._next_publish_at: datetime | None = None
        self._remaining_seconds: int = 0
        self._publish_in_progress: bool = False
        self._quit_binding_q = None
        self._quit_binding_cyrillic = None
        self._areas: list[AreaOption] = []
        self._roles: list[RoleOption] = []
        self._selected_area_id: str | None = None
        self._selected_role_ids: list[str] = []
        self._initial_config: dict[str, Any] = {}
        self._form_loaded = False
        self._confirm_dialog_active = False
        self._initial_theme_name: str | None = None
        self._preview_theme_name: str | None = None
        self._theme_committed: bool = False

    LAYOUT_SECTIONS: ClassVar[tuple[LayoutSectionDef, ...]] = (
        LayoutSectionDef(
            "Экран поиска вакансий",
            (
                LayoutField(
                    "Ширина панели \"Вакансии\" (%)",
                    "vacancy_pane_percent",
                    ConfigKeys.VACANCY_LEFT_PANE_PERCENT,
                    min_value=10,
                    max_value=90,
                ),
                LayoutField(
                    "Колонка \"№\" (симв.)",
                    "vacancy_col_index_width",
                    ConfigKeys.VACANCY_COL_INDEX_WIDTH,
                    max_value=COLUMN_WIDTH_MAX,
                ),
                LayoutField(
                    "Колонка \"Название\" (симв.)",
                    "vacancy_col_title_width",
                    ConfigKeys.VACANCY_COL_TITLE_WIDTH,
                    max_value=COLUMN_WIDTH_MAX,
                ),
                LayoutField(
                    "Колонка \"Компания\" (симв.)",
                    "vacancy_col_company_width",
                    ConfigKeys.VACANCY_COL_COMPANY_WIDTH,
                    max_value=COLUMN_WIDTH_MAX,
                ),
                LayoutField(
                    "Колонка \"Откликался\" (симв.)",
                    "vacancy_col_previous_width",
                    ConfigKeys.VACANCY_COL_PREVIOUS_WIDTH,
                    max_value=COLUMN_WIDTH_MAX,
                ),
            ),
            "display-settings-group--vacancy",
        ),
        LayoutSectionDef(
            "Экран истории откликов",
            (
                LayoutField(
                    "Ширина панели \"История\" (%)",
                    "history_pane_percent",
                    ConfigKeys.HISTORY_LEFT_PANE_PERCENT,
                    min_value=10,
                    max_value=90,
                ),
                LayoutField(
                    "Колонка \"№\" (симв.)",
                    "history_col_index_width",
                    ConfigKeys.HISTORY_COL_INDEX_WIDTH,
                    max_value=COLUMN_WIDTH_MAX,
                ),
                LayoutField(
                    "Колонка \"Название\" (симв.)",
                    "history_col_title_width",
                    ConfigKeys.HISTORY_COL_TITLE_WIDTH,
                    max_value=COLUMN_WIDTH_MAX,
                ),
                LayoutField(
                    "Колонка \"Компания\" (симв.)",
                    "history_col_company_width",
                    ConfigKeys.HISTORY_COL_COMPANY_WIDTH,
                    max_value=COLUMN_WIDTH_MAX,
                ),
                LayoutField(
                    "Колонка \"Статус\" (симв.)",
                    "history_col_status_width",
                    ConfigKeys.HISTORY_COL_STATUS_WIDTH,
                    max_value=COLUMN_WIDTH_MAX,
                ),
                LayoutField(
                    "Колонка \"✉\" (симв.)",
                    "history_col_sent_width",
                    ConfigKeys.HISTORY_COL_SENT_WIDTH,
                    max_value=COLUMN_WIDTH_MAX,
                ),
                LayoutField(
                    "Колонка \"Дата отклика\" (симв.)",
                    "history_col_date_width",
                    ConfigKeys.HISTORY_COL_DATE_WIDTH,
                    max_value=COLUMN_WIDTH_MAX,
                ),
            ),
            "display-settings-group--history",
        ),
    )

    LAYOUT_FIELDS: ClassVar[tuple[LayoutField, ...]] = tuple(
        field for section in LAYOUT_SECTIONS for field in section.fields
    )

    def compose(self) -> ComposeResult:
        with Vertical(id="config_screen"):
            yield Header(show_clock=True, name="hhcli - Настройки")
            with VerticalScroll(id="config-form"):
                yield Static("Параметры поиска", classes="header")
                yield Label("Ключевые слова для поиска (через запятую):")
                yield Input(id="text_include", placeholder='Python developer, Backend developer')
                yield Label("Исключающие слова (через запятую):")
                yield Input(id="negative", placeholder="senior, C++, DevOps, аналитик")

                yield Label("Формат работы:")
                yield Select([], id="work_format")

                with Horizontal(id="pickers-container"):
                    with Vertical(id="area-picker-container", classes="picker-group"):
                        yield Label("Регион / город поиска:", classes="summary-label")
                        yield Static("-", id="area_summary", classes="value-display")
                        yield Button("Выбрать регион", id="area_picker")

                    with Vertical(id="role-picker-container", classes="picker-group"):
                        yield Label("Профессиональные роли:", classes="summary-label")
                        yield Static("-", id="roles_summary", classes="value-display")
                        yield Button("Выбрать роли", id="roles_picker")

                yield Label("Область поиска:")
                yield Select(
                    [
                        ("В названии вакансии", "name"),
                        ("В названии компании", "company_name"),
                        ("В описании вакансии", "description"),
                    ],
                    id="search_field",
                )

                yield Label("Период публикации (дней, 1-30):")
                yield Input(id="period", placeholder="3")

                yield Static("Переключатели", classes="header")
                with Horizontal(id="switches-block", classes="switches-block"):
                    with Vertical(id="switches-list", classes="switches-list"):
                        yield Horizontal(
                            Switch(id="skip_applied_in_same_company"),
                            Label("Пропускать компании, куда уже был отклик", classes="switch-label"),
                            classes="switch-container",
                        )
                        yield Horizontal(
                            Switch(id="deduplicate_by_name_and_company"),
                            Label("Убирать дубли по 'Название+Компания'", classes="switch-label"),
                            classes="switch-container",
                        )
                        yield Horizontal(
                            Switch(id="strikethrough_applied_vac"),
                            Label("Зачеркивать вакансии по точному ID", classes="switch-label"),
                            classes="switch-container",
                        )
                        yield Horizontal(
                            Switch(id="strikethrough_applied_vac_name"),
                            Label("Зачеркивать вакансии по 'Название+Компания'", classes="switch-label"),
                            classes="switch-container",
                        )
                        yield Horizontal(
                            Switch(id="auto_raise_resume"),
                            Label("Поднимать резюме автоматически", classes="switch-label"),
                            classes="switch-container",
                        )
                    with Vertical(id="auto_raise_panel", classes="raise-timer-panel"):
                        yield Static("Автоподнятие резюме", classes="raise-timer-title")
                        yield Static("", id="auto_raise_status", classes="raise-timer-status")
                        yield Static(
                            self._render_big_time("--:--"),
                            id="auto_raise_timer",
                            classes="raise-timer-display",
                        )
                        yield Static("", id="auto_raise_hint", classes="raise-timer-hint")

                yield Static("Оформление", classes="header")
                yield Label("Тема интерфейса:")
                yield Select([], id="theme")

                yield Static("Настройки отображения экранов", classes="header")
                with Horizontal(id="display-settings-container", classes="display-settings-grid"):
                    for section in self.LAYOUT_SECTIONS:
                        with Vertical(classes=f"display-settings-group {section.css_class}") as group:
                            group.border_title = section.title
                            group.styles.border_title_align = "left"
                            for field in section.fields:
                                yield self._make_layout_row(field.label, field.input_id)

                yield Static("Сопроводительное письмо", classes="header")
                yield TextArea(id="cover_letter", language="markdown")

                yield Button("Сохранить и выйти", variant="success", id="save-button")

            yield Footer()

    def on_mount(self) -> None:
        """При монтировании временно отключаем глобальные биндинги выхода"""
        bindings_map = self.app._bindings
        self._quit_binding_q = bindings_map.key_to_bindings.pop("q", None)
        self._quit_binding_cyrillic = bindings_map.key_to_bindings.pop("й", None)
        self._refresh_raise_state()

        self.run_worker(self._load_data_worker, thread=True)

    def on_unmount(self) -> None:
        """При размонтировании возвращаем биндинги и останавливаем таймеры"""
        bindings_map = self.app._bindings
        if self._quit_binding_q:
            bindings_map.key_to_bindings['q'] = self._quit_binding_q
        if self._quit_binding_cyrillic:
            bindings_map.key_to_bindings['й'] = self._quit_binding_cyrillic
        if self._raise_timer:
            self._raise_timer.stop()
            self._raise_timer = None

    def _load_data_worker(self) -> None:
        """Работает в фоне и загружает данные, не взаимодействуя с виджетами"""
        profile_name = self.app.client.profile_name
        config = load_profile_config(profile_name)
        work_formats = self.app.dictionaries.get("work_format", [])
        areas = list_areas()
        roles = list_professional_roles()
        if not areas or not roles:
            try:
                ensure_reference_data(self.app.client)
            except Exception as exc:
                log_to_db("ERROR", LogSource.CONFIG_SCREEN, f"Не удалось обновить справочники: {exc}")
                pass
            areas = list_areas()
            roles = list_professional_roles()

        if not areas:
            self.app.call_from_thread(
                self.app.notify,
                "Не удалось загрузить справочник городов.",
                severity="warning",
            )
            log_to_db("WARN", LogSource.CONFIG_SCREEN, "Справочник городов недоступен")
        if not roles:
            self.app.call_from_thread(
                self.app.notify,
                "Не удалось загрузить справочник профессиональных ролей.",
                severity="warning",
            )
            log_to_db("WARN", LogSource.CONFIG_SCREEN, "Справочник профессиональных ролей недоступен")

        self.app.call_from_thread(self._populate_form, config, work_formats, areas, roles)

    def _populate_form(
        self,
        config: dict,
        work_formats: list,
        areas: list[dict],
        roles: list[dict],
    ) -> None:
        """Работает в основном потоке и наполняет форму данными"""
        defaults = get_default_config()
        work_format_options = [(item["name"], str(item["id"])) for item in work_formats]
        configured_work_format = config.get(ConfigKeys.WORK_FORMAT)
        default_work_format = defaults.get(ConfigKeys.WORK_FORMAT)
        existing_values = {value for _, value in work_format_options}
        for value in (configured_work_format, default_work_format):
            if value and value not in existing_values:
                work_format_options.append((str(value), str(value)))
                existing_values.add(value)
        if not work_format_options:
            work_format_options.append(("Не выбрано", Select.BLANK))
        self.query_one("#work_format", Select).set_options(work_format_options)

        self.query_one("#text_include", Input).value = ", ".join(config.get(ConfigKeys.TEXT_INCLUDE, []))
        self.query_one("#negative", Input).value = ", ".join(config.get(ConfigKeys.NEGATIVE, []))
        _set_select_value(self.query_one("#work_format", Select), configured_work_format)
        _set_select_value(self.query_one("#search_field", Select), config.get(ConfigKeys.SEARCH_FIELD))
        self.query_one("#period", Input).value = config.get(ConfigKeys.PERIOD, "")
        self.query_one("#cover_letter", TextArea).load_text(config.get(ConfigKeys.COVER_LETTER, ""))
        self.query_one("#skip_applied_in_same_company", Switch).value = config.get(ConfigKeys.SKIP_APPLIED_IN_SAME_COMPANY, False)
        self.query_one("#deduplicate_by_name_and_company", Switch).value = config.get(ConfigKeys.DEDUPLICATE_BY_NAME_AND_COMPANY, True)
        self.query_one("#strikethrough_applied_vac", Switch).value = config.get(ConfigKeys.STRIKETHROUGH_APPLIED_VAC, True)
        self.query_one("#strikethrough_applied_vac_name", Switch).value = config.get(ConfigKeys.STRIKETHROUGH_APPLIED_VAC_NAME, True)
        self.query_one("#auto_raise_resume", Switch).value = config.get(ConfigKeys.AUTO_RAISE_RESUME, False)

        manager = self.app.css_manager
        manager.reload_themes()

        self._areas = [
            AreaOption(
                id=str(area["id"]),
                label=area["full_name"],
                search_text=_normalize(f"{area['full_name']} {area['name']} {area['id']}"),
            )
            for area in areas
        ]
        self._roles = [
            RoleOption(
                id=str(role["id"]),
                label=f"{role['category_name']} — {role['name']}",
                search_text=_normalize(f"{role['category_name']} {role['name']} {role['id']}"),
            )
            for role in roles
        ]

        self._selected_area_id = config.get(ConfigKeys.AREA_ID) or None
        raw_roles = config.get(ConfigKeys.ROLE_IDS_CONFIG, [])
        self._selected_role_ids = [str(rid) for rid in raw_roles if str(rid)]

        self._update_area_summary()
        self._update_roles_summary()

        theme_select = self.query_one("#theme", Select)
        themes = sorted(manager.themes.values(), key=lambda t: t._name)
        theme_select.set_options(
            [
                (self._beautify_theme_name(theme._name), theme._name)
                for theme in themes
            ]
        )
        configured_theme = config.get(ConfigKeys.THEME)
        if configured_theme not in manager.themes:
            configured_theme = manager.theme._name
        theme_select.value = configured_theme or manager.theme._name

        current_theme_name = manager.theme._name
        self._initial_theme_name = current_theme_name
        self._preview_theme_name = current_theme_name
        self._theme_committed = False
        self._populate_layout_settings(config, defaults)
        self._initial_config = self._current_form_config()
        self._form_loaded = True
        self._refresh_raise_state()

    def _update_area_summary(self) -> None:
        summary_widget = self.query_one("#area_summary", Static)
        if not self._selected_area_id:
            summary_widget.update("[dim]Не выбрано[/dim]")
            return
        label = self._find_area_label(self._selected_area_id)
        summary_widget.update(label or "[dim]Не выбрано[/dim]")

    def _update_roles_summary(self) -> None:
        summary_widget = self.query_one("#roles_summary", Static)
        if not self._selected_role_ids:
            summary_widget.update("[dim]Не выбрано[/dim]")
            return
        labels = self._find_role_labels(self._selected_role_ids)
        if not labels:
            summary_widget.update("[dim]Не выбрано[/dim]")
            return
        if len(labels) > 3:
            summary_widget.update(", ".join(labels[:3]) + f" [+ ещё {len(labels) - 3}]")
        else:
            summary_widget.update(", ".join(labels))

    def _find_area_label(self, area_id: str) -> str | None:
        for option in self._areas:
            if option.id == area_id:
                return option.label
        return None

    def _find_role_labels(self, role_ids: list[str]) -> list[str]:
        cache = {option.id: option.label for option in self._roles}
        return [cache[rid] for rid in role_ids if rid in cache]

    @staticmethod
    def _beautify_theme_name(theme_name: str) -> str:
        name = theme_name.removeprefix("hhcli-").replace("-", " ")
        return name.title() or theme_name

    def _apply_theme_preview(self, theme_value: object | None) -> None:
        if not self.app or not self.app.css_manager:
            return
        resolved = _theme_value(theme_value)
        theme_key = (resolved or "hhcli-base").strip() or "hhcli-base"
        if self._preview_theme_name == theme_key:
            return
        try:
            self.app.css_manager.set_theme(theme_key)
            self._preview_theme_name = theme_key
        except ValueError:
            log_to_db(
                "WARN",
                LogSource.CONFIG_SCREEN,
                f"Предпросмотр темы '{theme_key}' недоступен.",
            )

    def _revert_theme_preview(self) -> None:
        if not self.app or not self.app.css_manager:
            return
        target = (self._initial_theme_name or "hhcli-base").strip() or "hhcli-base"
        if self._preview_theme_name == target:
            return
        try:
            self.app.css_manager.set_theme(target)
            self._preview_theme_name = target
        except ValueError:
            log_to_db(
                "WARN",
                LogSource.CONFIG_SCREEN,
                f"Возврат темы '{target}' невозможен, применяется базовая.",
            )
            self.app.css_manager.set_theme("hhcli-base")
            self._preview_theme_name = "hhcli-base"

    def _make_layout_row(self, label_text: str, input_id: str) -> Horizontal:
        return Horizontal(
            Label(label_text, classes="display-settings-label"),
            Input(id=input_id, classes="display-settings-input"),
            classes="display-settings-row",
        )

    def _parse_int_value(
        self,
        selector: str,
        fallback: int,
        *,
        min_value: int = 1,
        max_value: int = 100,
    ) -> int:
        raw = self.query_one(selector, Input).value.strip()
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = fallback
        return max(min_value, min(max_value, value))

    def _current_form_config(self) -> dict[str, Any]:
        """Возвращает текущее состояние формы как словарь конфигурации"""
        def parse_list(text: str) -> list[str]:
            return [item.strip() for item in text.split(",") if item.strip()]

        defaults = get_default_config()
        initial = getattr(self, "_initial_config", {})

        def int_setting(selector: str, key: str, *, min_value: int = 1, max_value: int = 100) -> int:
            fallback = initial.get(key, defaults[key])
            return self._parse_int_value(selector, fallback, min_value=min_value, max_value=max_value)

        config_snapshot = {
            ConfigKeys.TEXT_INCLUDE: parse_list(self.query_one("#text_include", Input).value),
            ConfigKeys.NEGATIVE: parse_list(self.query_one("#negative", Input).value),
            ConfigKeys.ROLE_IDS_CONFIG: list(self._selected_role_ids),
            ConfigKeys.WORK_FORMAT: _select_value(self.query_one("#work_format", Select)),
            ConfigKeys.AREA_ID: self._selected_area_id or "",
            ConfigKeys.SEARCH_FIELD: _select_value(self.query_one("#search_field", Select)),
            ConfigKeys.PERIOD: self.query_one("#period", Input).value,
            ConfigKeys.COVER_LETTER: self.query_one("#cover_letter", TextArea).text,
            ConfigKeys.SKIP_APPLIED_IN_SAME_COMPANY: self.query_one("#skip_applied_in_same_company", Switch).value,
            ConfigKeys.DEDUPLICATE_BY_NAME_AND_COMPANY: self.query_one("#deduplicate_by_name_and_company", Switch).value,
            ConfigKeys.STRIKETHROUGH_APPLIED_VAC: self.query_one("#strikethrough_applied_vac", Switch).value,
            ConfigKeys.STRIKETHROUGH_APPLIED_VAC_NAME: self.query_one("#strikethrough_applied_vac_name", Switch).value,
            ConfigKeys.AUTO_RAISE_RESUME: self.query_one("#auto_raise_resume", Switch).value,
            ConfigKeys.THEME: _theme_value(self.query_one("#theme", Select).value) or "hhcli-base",
        }
        for field in self.LAYOUT_FIELDS:
            config_snapshot[field.config_key] = int_setting(
                field.selector,
                field.config_key,
                min_value=field.min_value,
                max_value=field.max_value,
            )
        return config_snapshot

    def _populate_layout_settings(self, config: dict[str, Any], defaults: dict[str, Any]) -> None:
        for field in self.LAYOUT_FIELDS:
            value = config.get(field.config_key, defaults[field.config_key])
            self.query_one(field.selector, Input).value = str(value)

    def _has_unsaved_changes(self) -> bool:
        if not self._form_loaded:
            return False
        return self._current_form_config() != self._initial_config

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-button":
            self.action_save_config()
        elif event.button.id == "area_picker":
            self._open_area_picker()
        elif event.button.id == "roles_picker":
            self._open_roles_picker()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "theme":
            return
        if not self._form_loaded:
            return
        self._apply_theme_preview(event.value)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "auto_raise_resume" and self._form_loaded:
            self._refresh_raise_state()

    def _open_area_picker(self) -> None:
        if not self._areas:
            self.app.notify("Справочник городов пуст.", severity="warning")
            return
        self.app.push_screen(
            AreaPickerDialog(self._areas, self._selected_area_id),
            self._on_area_picker_closed,
        )

    def _open_roles_picker(self) -> None:
        if not self._roles:
            self.app.notify("Справочник ролей пуст.", severity="warning")
            return
        self.app.push_screen(
            RolePickerDialog(self._roles, self._selected_role_ids),
            self._on_roles_picker_closed,
        )

    def _on_area_picker_closed(self, area_id: str | None) -> None:
        self._selected_area_id = area_id
        self._update_area_summary()

    def _on_roles_picker_closed(self, role_ids: list[str] | None) -> None:
        if role_ids is None:
            return
        self._selected_role_ids = role_ids
        self._update_roles_summary()

    def action_cancel(self) -> None:
        """Закрывает экран и при необходимости спрашивает подтверждение"""
        if not self._has_unsaved_changes():
            self.dismiss(False)
            return
        if self._confirm_dialog_active:
            return
        self._confirm_dialog_active = True
        self.app.push_screen(
            ConfigUnsavedChangesDialog(),
            self._on_unsaved_dialog_closed,
        )

    def action_save_config(self) -> None:
        """Собирает данные с формы и сохраняет их в базе"""
        profile_name = self.app.client.profile_name
        config = self._current_form_config()
        auto_raise_was_enabled = bool(self._initial_config.get(ConfigKeys.AUTO_RAISE_RESUME, False))
        auto_raise_enabled_now = bool(config.get(ConfigKeys.AUTO_RAISE_RESUME, False))
        auto_raise_activated = auto_raise_enabled_now and not auto_raise_was_enabled

        save_profile_config(profile_name, config)
        self.app.apply_theme_from_profile(profile_name)
        self._theme_committed = True
        self._initial_theme_name = self.app.css_manager.theme._name
        self._preview_theme_name = self._initial_theme_name
        self._initial_config = config
        if auto_raise_activated and self.resume_id:
            self._auto_publish_resume(trigger="save")
        else:
            self._refresh_raise_state()
        self.app.notify("Настройки успешно сохранены.", title="Успех", severity="information")
        self.dismiss(True)

    def _on_unsaved_dialog_closed(self, decision: str | None) -> None:
        self._confirm_dialog_active = False
        if decision == "save":
            self.action_save_config()
        elif decision == "discard":
            self.dismiss(False)

    def dismiss(self, result=None) -> None:  # type: ignore[override]
        if not self._theme_committed:
            self._revert_theme_preview()
        super().dismiss(result)

    def _render_big_time(self, text: str) -> str:
        glyphs = [TIMER_GLYPHS.get(char, TIMER_GLYPHS[" "]) for char in text]
        if not glyphs:
            return ""

        base_width = len(glyphs[0][0])
        base_height = len(glyphs[0])
        spacing = 2

        available_width = max(40, getattr(self.size, "width", 0) - 8)
        available_height = max(10, getattr(self.size, "height", 0) // 3)
        try:
            timer = self.query_one("#auto_raise_timer", Static)
            available_width = max(available_width, getattr(timer.size, "width", 0) or 0)
            available_height = max(available_height, getattr(timer.size, "height", 0) or 0)
        except Exception:
            pass

        def fits(scale: int) -> bool:
            total_width = len(glyphs) * (base_width * scale) + (len(glyphs) - 1) * (spacing * scale)
            total_height = base_height * scale
            return total_width <= available_width and total_height <= available_height

        scale = 1
        for candidate in (3, 2, 1):
            if fits(candidate):
                scale = candidate
                break

        scaled_rows: list[str] = []
        separator = " " * (spacing * scale)
        for row_parts in zip(*glyphs):
            stretched = separator.join("".join(ch * scale for ch in part) for part in row_parts)
            for _ in range(scale):
                scaled_rows.append(stretched)

        return "\n".join(scaled_rows)

    def _render_big_time_from_seconds(self, seconds: int | None) -> str:
        return self._render_big_time(self._format_remaining(seconds))

    def _auto_raise_current_value(self) -> bool:
        try:
            return bool(self.query_one("#auto_raise_resume", Switch).value)
        except Exception:
            return False

    def _auto_raise_committed_value(self) -> bool:
        return bool(self._initial_config.get(ConfigKeys.AUTO_RAISE_RESUME, False))

    def _auto_raise_toggle_dirty(self) -> bool:
        return self._auto_raise_current_value() != self._auto_raise_committed_value()

    def _auto_raise_is_active(self) -> bool:
        return bool(self.resume_id) and self._auto_raise_committed_value()

    def _update_raise_card(self, status: str, remaining: int | None, *, hint: str | None = None) -> None:
        try:
            timer = self.query_one("#auto_raise_timer", Static)
            status_label = self.query_one("#auto_raise_status", Static)
            hint_label = self.query_one("#auto_raise_hint", Static)
        except Exception:
            return
        timer.update(self._render_big_time_from_seconds(remaining))
        status_label.update(status)
        hint_label.update(hint or "")

    def _stop_raise_timer(self) -> None:
        if self._raise_timer:
            self._raise_timer.stop()
            self._raise_timer = None

    def _refresh_raise_state(self) -> None:
        self._stop_raise_timer()
        if not self.resume_id:
            self._remaining_seconds = 0
            self._update_raise_card("Резюме не выбрано.", None, hint="Выберите резюме, чтобы включить автоподнятие.")
            return

        if self._auto_raise_toggle_dirty():
            hint = (
                "Сохраните настройки, чтобы включить автоподнятие."
                if self._auto_raise_current_value()
                else "Сохраните настройки, чтобы отключить автоподнятие."
            )
            self._update_raise_card("Изменения не сохранены.", None, hint=hint)
            return

        if not self._auto_raise_is_active():
            self._remaining_seconds = 0
            self._update_raise_card("Автоподнятие выключено.", None, hint="Включите переключатель и сохраните настройки.")
            return

        self._update_raise_card("Обновляем статус резюме...", None)
        self.run_worker(self._raise_state_worker(), thread=True, exclusive=False)

    async def _raise_state_worker(self):
        if not self.resume_id:
            return
        try:
            data = self.app.client.get_resume_details(self.resume_id)
            next_raw = data.get("next_publish_at")
            can_publish = data.get("can_publish_or_update", True)
            next_dt = _parse_iso(next_raw)
            remaining = 0
            if next_dt:
                delta = next_dt - datetime.now(tz=next_dt.tzinfo)
                remaining = max(0, int(delta.total_seconds()))
            self.app.call_from_thread(self._apply_raise_state, remaining, bool(can_publish))
        except AuthorizationPending:
            self.app.call_from_thread(
                self._update_raise_card,
                "Требуется авторизация для автоподнятия.",
                None,
                hint="Войдите заново и сохраните настройки.",
            )
        except Exception as exc:
            self.app.call_from_thread(
                self._update_raise_card,
                f"Ошибка статуса резюме: {exc}",
                None,
                hint="Проверьте соединение и попробуйте снова.",
            )
            self.app.call_from_thread(self._apply_raise_state, 0, False)

    def _apply_raise_state(self, remaining: int, can_publish: bool) -> None:
        self._remaining_seconds = max(0, remaining)
        if not self.resume_id:
            self._stop_raise_timer()
            self._update_raise_card("Резюме не выбрано.", None, hint="Выберите резюме, чтобы включить автоподнятие.")
            return

        if self._auto_raise_toggle_dirty():
            self._stop_raise_timer()
            hint = (
                "Сохраните настройки, чтобы включить автоподнятие."
                if self._auto_raise_current_value()
                else "Сохраните настройки, чтобы отключить автоподнятие."
            )
            self._update_raise_card("Изменения не сохранены.", None, hint=hint)
            return

        if not self._auto_raise_is_active():
            self._stop_raise_timer()
            self._update_raise_card("Автоподнятие выключено.", None, hint="Включите переключатель и сохраните настройки.")
            return

        if not can_publish:
            self._publish_in_progress = False
            if self._remaining_seconds > 0:
                self._update_raise_card(
                    f"Следующее поднятие через {self._format_remaining(self._remaining_seconds)}",
                    self._remaining_seconds,
                )
                self._start_raise_timer()
            else:
                self._stop_raise_timer()
                self._update_raise_card("Поднятие недоступно для выбранного резюме.", None)
            return

        if self._remaining_seconds <= 0:
            if self._publish_in_progress:
                self._update_raise_card("Поднимаем резюме...", 0)
                return
            self._update_raise_card("Поднимаем резюме...", 0)
            self._auto_publish_resume(trigger="state")
            return

        self._update_raise_card(
            f"Следующее поднятие через {self._format_remaining(self._remaining_seconds)}",
            self._remaining_seconds,
        )
        self._start_raise_timer()

    def _start_raise_timer(self) -> None:
        self._stop_raise_timer()
        if self._remaining_seconds <= 0:
            return
        self._raise_timer = self.set_interval(1.0, self._on_raise_tick, pause=False)

    def _on_raise_tick(self) -> None:
        if self._remaining_seconds <= 0:
            self._stop_raise_timer()
            self._apply_raise_state(0, True)
            return
        self._remaining_seconds = max(0, self._remaining_seconds - 1)
        self._update_raise_card(
            f"Следующее поднятие через {self._format_remaining(self._remaining_seconds)}",
            self._remaining_seconds,
        )

    def _format_remaining(self, seconds: int | None) -> str:
        if seconds is None or seconds < 0:
            return "--:--"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d}"

    def _auto_publish_resume(self, *, trigger: str = "auto") -> None:
        if self._publish_in_progress or not self.resume_id:
            return
        self._publish_in_progress = True
        log_to_db(
            "INFO",
            LogSource.CONFIG_SCREEN,
            f"Автоподнятие резюме {self.resume_id} (trigger={trigger})",
        )
        self._update_raise_card("Поднимаем резюме...", 0)
        self.run_worker(self._auto_publish_worker(trigger), thread=True, exclusive=False)

    async def _auto_publish_worker(self, trigger: str):
        try:
            self.app.client.publish_resume(self.resume_id)
            self.app.call_from_thread(
                self.app.notify,
                "Резюме поднято автоматически",
                title="Автоподнятие",
                timeout=2,
            )
        except AuthorizationPending:
            self.app.call_from_thread(
                self.app.notify,
                "Требуется авторизация для поднятия резюме.",
                severity="warning",
                timeout=4,
            )
        except Exception as exc:
            self.app.call_from_thread(
                self.app.notify,
                f"Не удалось поднять резюме: {exc}",
                severity="error",
                timeout=4,
            )
        finally:
            self.app.call_from_thread(self._on_auto_publish_finished)

    def _on_auto_publish_finished(self) -> None:
        self._publish_in_progress = False
        self._refresh_raise_state()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except Exception:
        return None
