from __future__ import annotations

import random

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical
from textual.widgets import Button, Input, Static
from textual.screen import ModalScreen


class ApplyConfirmationDialog(ModalScreen[str | None]):
    """Модальное окно подтверждения массовой отправки откликов"""

    BINDINGS = [
        Binding("escape", "cancel", "Отмена", show=True, key_display="Esc"),
    ]

    def __init__(self, count: int) -> None:
        super().__init__()
        self.count = count
        self.confirm_code = str(random.randint(1000, 9999))

    def compose(self) -> ComposeResult:
        with Center(id="config-confirm-center"):
            with Vertical(id="config-confirm-dialog", classes="config-confirm") as dialog:
                dialog.border_title = "Подтверждение"
                dialog.styles.border_title_align = "left"
                yield Static(
                    "Если вы уверены, что хотите отправить отклики в выбранные компании, "
                    f"введите число: [b green]{self.confirm_code}[/]",
                    classes="config-confirm__message",
                    expand=True,
                )
                yield Static("", id="apply_confirm_error")
                yield Center(
                    Input(
                        placeholder="Введите число здесь...",
                        id="apply_confirm_input",
                    )
                )
                with Horizontal(classes="config-confirm__buttons"):
                    yield Button("Отправить", id="confirm-submit", variant="success")
                    yield Button("Сброс", id="confirm-reset", classes="decline")
                    yield Button("Отмена", id="confirm-cancel")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._attempt_submit(event.value, event.input)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-submit":
            input_widget = self.query_one("#apply_confirm_input", Input)
            self._attempt_submit(input_widget.value, input_widget)
        elif event.button.id == "confirm-reset":
            self.dismiss("reset")
        elif event.button.id == "confirm-cancel":
            self.dismiss("cancel")

    def action_cancel(self) -> None:
        self.dismiss("cancel")

    def _attempt_submit(self, value: str, input_widget: Input) -> None:
        if value.strip() == self.confirm_code:
            self.dismiss("submit")
            return
        self.query_one("#apply_confirm_error", Static).update(
            "[b red]Неверное число. Попробуйте ещё раз.[/b red]"
        )
        input_widget.value = ""
        input_widget.focus()


__all__ = ["ApplyConfirmationDialog"]
