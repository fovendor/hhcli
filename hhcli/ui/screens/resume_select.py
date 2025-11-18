from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header

from ...constants import LogSource
from ...database import log_to_db
from .search_mode import SearchModeScreen


class ResumeSelectionScreen(Screen):
    """Экран выбора резюме перед запуском поиска"""

    def __init__(self, resume_data: dict) -> None:
        super().__init__()
        self.resume_data = resume_data
        self.index_to_resume_id: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, name="hh-cli")
        yield DataTable(id="resume_table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Должность", "Ссылка")
        self.index_to_resume_id.clear()

        items = self.resume_data.get("items", [])
        if not items:
            table.add_row("[b]У вас нет ни одного резюме.[/b]")
            return

        for r in items:
            table.add_row(f"[bold green]{r.get('title')}[/bold green]", r.get("alternate_url"))
            self.index_to_resume_id.append(r.get("id"))

    def on_data_table_row_selected(self, _: DataTable.RowSelected) -> None:
        table = self.query_one(DataTable)
        idx = table.cursor_row
        if idx is None or idx < 0 or idx >= len(self.index_to_resume_id):
            return
        resume_id = self.index_to_resume_id[idx]
        resume_title = ""
        for r in self.resume_data.get("items", []):
            if r.get("id") == resume_id:
                resume_title = r.get("title") or ""
                break
        log_to_db(
            "INFO",
            LogSource.RESUME_SCREEN,
            f"Выбрано резюме: {resume_id} '{resume_title}'",
        )
        self.app.push_screen(
            SearchModeScreen(
                resume_id=resume_id,
                resume_title=resume_title,
                is_root_screen=False,
            )
        )

    def on_screen_resume(self) -> None:
        self.app.apply_theme_from_profile(self.app.client.profile_name)


__all__ = ["ResumeSelectionScreen"]
