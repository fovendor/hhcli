from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class ProfileCreateDialog(ModalScreen[str | None]):
    """Модальное окно создания нового профиля."""

    BINDINGS = [
        Binding("escape", "cancel", "Отмена", show=True, key_display="Esc"),
    ]

    def compose(self) -> ComposeResult:
        with Center(id="profile-create-center"):
            with Vertical(id="profile-create-dialog") as dialog:
                dialog.border_title = "Новый профиль"
                dialog.styles.border_title_align = "left"
                yield Input(placeholder="Например: analyst", id="profile-create-input")
                with Horizontal(id="profile-create-buttons"):
                    yield Button("Создать", id="profile-create-submit", variant="primary", disabled=True)
                    yield Button("Отмена", id="profile-create-cancel")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "profile-create-input":
            submit = self.query_one("#profile-create-submit", Button)
            submit.disabled = len(event.value.strip()) == 0

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "profile-create-input":
            return
        value = event.value.strip()
        submit = self.query_one("#profile-create-submit", Button)
        if value and not submit.disabled:
            self.dismiss(value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "profile-create-submit" and not event.button.disabled:
            value = self.query_one("#profile-create-input", Input).value.strip()
            if value:
                self.dismiss(value)
        elif event.button.id == "profile-create-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


__all__ = ["ProfileCreateDialog"]
