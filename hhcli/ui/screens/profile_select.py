from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from ...constants import LogSource
from ...database import log_to_db, set_active_profile


class ProfileSelectionScreen(Screen):
    """Экран выбора профиля, когда в базе их несколько"""

    def __init__(self, all_profiles: list[dict]) -> None:
        super().__init__()
        self.all_profiles = all_profiles
        self.index_to_profile: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, name="hh-cli")
        yield Static("[b]Выберите профиль:[/b]\n")
        yield DataTable(id="profile_table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Имя профиля", "Email")
        self.index_to_profile.clear()
        for p in self.all_profiles:
            table.add_row(f"[bold green]{p['profile_name']}[/bold green]", p["email"])
            self.index_to_profile.append(p["profile_name"])

    def on_data_table_row_selected(self, _: DataTable.RowSelected) -> None:
        table = self.query_one(DataTable)
        idx = table.cursor_row
        if idx is None or idx < 0 or idx >= len(self.index_to_profile):
            return
        profile_name = self.index_to_profile[idx]
        log_to_db("INFO", LogSource.PROFILE_SCREEN, f"Выбран профиль '{profile_name}'")
        set_active_profile(profile_name)
        self.dismiss(profile_name)


__all__ = ["ProfileSelectionScreen"]
