from __future__ import annotations

import random
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class CodeConfirmationDialog(ModalScreen[str | None]):
    """Универсальная модалка для подтверждения действий вводом кода."""

    BINDINGS = [Binding("escape", "cancel", "Отмена", show=True, key_display="Esc")]

    def __init__(
        self,
        *,
        title: str,
        message: str,
        confirm_label: str,
        confirm_variant: str = "primary",
        cancel_label: str = "Отмена",
        reset_label: str | None = None,
        reset_result: str = "reset",
        code: str | None = None,
        message_vars: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.title = title
        self.message_template = message
        self.confirm_label = confirm_label
        self.confirm_variant = confirm_variant
        self.cancel_label = cancel_label
        self.reset_label = reset_label
        self.reset_result = reset_result
        self.confirm_code = str(code or random.randint(1000, 9999))
        self.message_vars = message_vars or {}

    def compose(self) -> ComposeResult:
        formatted_message = self.message_template.format(code=self.confirm_code, **self.message_vars)
        with Center(id="config-confirm-center"):
            with Vertical(id="config-confirm-dialog", classes="config-confirm code-confirm") as dialog:
                dialog.border_title = self.title
                dialog.styles.border_title_align = "left"
                yield Static(formatted_message, classes="config-confirm__message", expand=True)
                yield Static("", id="confirm_code_error", classes="code-confirm__error")
                yield Center(
                    Input(
                        placeholder="Введите число здесь...",
                        id="confirm_code_input",
                        classes="code-confirm__input",
                    )
                )
                with Horizontal(classes="config-confirm__buttons"):
                    if self.reset_label:
                        yield Button(self.reset_label, id="code-confirm-reset", classes="decline")
                    yield Button(self.confirm_label, id="code-confirm-submit", variant=self.confirm_variant)
                    yield Button(self.cancel_label, id="code-confirm-cancel")

    def on_mount(self) -> None:
        self.query_one("#confirm_code_input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "confirm_code_input":
            self._attempt_submit(event.value, event.input)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "code-confirm-submit":
            input_widget = self.query_one("#confirm_code_input", Input)
            self._attempt_submit(input_widget.value, input_widget)
        elif event.button.id == "code-confirm-reset":
            self.dismiss(self.reset_result)
        elif event.button.id == "code-confirm-cancel":
            self.dismiss("cancel")

    def action_cancel(self) -> None:
        self.dismiss("cancel")

    def _attempt_submit(self, value: str, input_widget: Input) -> None:
        if value.strip() == self.confirm_code:
            self.dismiss("submit")
            return
        self.query_one("#confirm_code_error", Static).update(
            "[b red]Неверное число. Попробуйте ещё раз.[/b red]"
        )
        input_widget.value = ""
        input_widget.focus()


__all__ = ["CodeConfirmationDialog"]
