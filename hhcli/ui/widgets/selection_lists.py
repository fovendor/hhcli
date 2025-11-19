from __future__ import annotations

from textual.events import MouseDown
from textual.widgets import SelectionList
from textual.widgets._option_list import OptionList


class VacancySelectionList(SelectionList[str]):
    """Список вакансий, где выбор делается только через клавиатуру"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._allow_toggle = False

    def toggle_current(self) -> None:
        """Переключает выделенную опцию программно, например по хоткею"""
        if self.highlighted is None:
            return
        self._allow_toggle = True
        self.action_select()
        if self._allow_toggle:
            self._allow_toggle = False

    def action_select(self) -> None:
        if not self._allow_toggle:
            return
        super().action_select()

    def _on_option_list_option_selected(
        self,
        event: OptionList.OptionSelected,
    ) -> None:
        if self._allow_toggle:
            self._allow_toggle = False
            super()._on_option_list_option_selected(event)
            return

        event.stop()
        self._allow_toggle = False
        if event.option_index != self.highlighted:
            self.highlighted = event.option_index
        else:
            self.post_message(
                self.SelectionHighlighted(self, event.option_index)
            )

    def on_mouse_down(self, event: MouseDown) -> None:
        if event.button != 1:
            event.stop()
            return
        self.focus()


class HistoryOptionList(OptionList):
    """Список истории без чекбоксов, работает только на чтение"""

    def on_mouse_down(self, event: MouseDown) -> None:
        if event.button != 1:
            event.stop()
            return
        self.focus()


__all__ = ["HistoryOptionList", "VacancySelectionList"]
