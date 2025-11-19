from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button


class PaginationButton(Button):
    """Кнопка пагинации с дополнительной мета-информацией."""

    def __init__(
        self,
        label: str,
        *,
        action: str,
        target_page: int | None = None,
        **kwargs,
    ) -> None:
        super().__init__(label, **kwargs)
        self.pagination_action = action
        self.pagination_target_page = target_page

class Pagination(Horizontal):
    """Виджет пагинации"""

    class PageChanged(Message):
        """Сообщение о смене страницы"""
        def __init__(self, page: int) -> None:
            super().__init__()
            self.page = page

    current_page = reactive(0)
    total_pages = reactive(1)

    def on_mount(self) -> None:
        self._rebuild_controls()

    def watch_current_page(self, old_page: int, new_page: int) -> None:
        self._rebuild_controls()

    def watch_total_pages(self, old_total: int, new_total: int) -> None:
        self._rebuild_controls()

    def update_state(self, current: int, total: int) -> None:
        """Обновляет состояние пагинации"""
        self.total_pages = total
        self.current_page = current

    def _rebuild_controls(self) -> None:
        """Перестраивает набор кнопок управления"""
        # Удаляем предыдущие кнопки, если они есть
        for child in list(self.children):
            child.remove()

        if self.total_pages <= 1:
            return

        pages_to_render = []
        if self.total_pages <= 3:
            pages_to_render = list(range(self.total_pages))
        elif self.current_page == 0:
            pages_to_render = [0, 1, 2]
        elif self.current_page == self.total_pages - 1:
            pages_to_render = [self.total_pages - 3, self.total_pages - 2, self.total_pages - 1]
        else:
            pages_to_render = [self.current_page - 1, self.current_page, self.current_page + 1]

        widgets = []
        # Кнопки "назад"
        widgets.append(
            PaginationButton(
                "<<",
                action="first",
                disabled=self.current_page == 0,
            )
        )
        widgets.append(
            PaginationButton(
                "<",
                action="prev",
                disabled=self.current_page == 0,
            )
        )

        # Кнопки с номерами страниц
        for page in pages_to_render:
            is_current = page == self.current_page
            widgets.append(
                PaginationButton(
                    str(page + 1),
                    action="page",
                    target_page=page,
                    variant="primary" if is_current else "default",
                    disabled=is_current,
                )
            )

        # Кнопки "вперед"
        widgets.append(
            PaginationButton(
                ">",
                action="next",
                disabled=self.current_page >= self.total_pages - 1,
            )
        )
        widgets.append(
            PaginationButton(
                ">>",
                action="last",
                disabled=self.current_page >= self.total_pages - 1,
            )
        )
        
        self.mount_all(widgets)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        # Проверяем, что кнопка принадлежит нашему типу, чтобы избежать случайных срабатываний
        if not isinstance(event.button, PaginationButton):
            return

        event.stop()
        button = event.button
        action = getattr(button, "pagination_action", None)
        if not action:
            return

        actions = {
            "first": 0,
            "last": self.total_pages - 1,
            "prev": self.current_page - 1,
            "next": self.current_page + 1,
        }
        target_page = actions.get(action)

        if target_page is None and action == "page":
            target_page = getattr(button, "pagination_target_page", None)

        if target_page is not None and 0 <= target_page < self.total_pages:
            self.post_message(self.PageChanged(page=target_page))
