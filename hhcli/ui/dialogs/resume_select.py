from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, OptionList, Static
from textual.widgets._option_list import Option


class ResumeSelectDialog(ModalScreen[tuple[str, str] | None]):
    """Модальное окно выбора резюме при наличии нескольких вариантов"""

    BINDINGS = [
        Binding("escape", "cancel", "Отмена", show=True, key_display="Esc"),
    ]

    def __init__(self, resumes: list[dict]) -> None:
        super().__init__()
        self.resumes = resumes
        self._selected_id: str | None = None
        self._id_to_title: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        with Center(id="resume-select-center"):
            with Vertical(id="resume-select-dialog") as dialog:
                dialog.border_title = "Выберите резюме"
                dialog.styles.border_title_align = "left"
                yield OptionList(id="resume-select-list")
                with Horizontal(id="resume-select-buttons"):
                    yield Button("Отмена", id="resume-select-cancel")

    def on_mount(self) -> None:
        option_list = self.query_one(OptionList)
        option_list.clear_options()
        for r in self.resumes:
            resume_id = r.get("id") or ""
            title = (r.get("title") or "").strip() or "Без названия"
            label = title
            self._id_to_title[resume_id] = title
            option_list.add_option(Option(label, resume_id))
        option_list.focus()

    def _set_selected(self, resume_id: str | None) -> None:
        self._selected_id = resume_id

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option and event.option.id:
            self._set_selected(str(event.option.id))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option.id
        if option_id:
            title = self._id_to_title.get(str(option_id), "")
            self.dismiss((str(option_id), title))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "resume-select-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


__all__ = ["ResumeSelectDialog"]
