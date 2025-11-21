from __future__ import annotations

from .confirm_code import CodeConfirmationDialog


class ApplyConfirmationDialog(CodeConfirmationDialog):
    """Модальное окно подтверждения массовой отправки откликов"""

    def __init__(self, count: int) -> None:
        self.count = count
        super().__init__(
            title="Подтверждение",
            message=(
                "Если вы уверены, что хотите отправить отклики в выбранные компании, "
                "введите число: [b green]{code}[/]"
            ),
            confirm_label="Отправить",
            confirm_variant="success",
            reset_label="Сброс",
        )


__all__ = ["ApplyConfirmationDialog"]
