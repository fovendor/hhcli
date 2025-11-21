"""Диалоги пользовательского интерфейса"""

from .apply_confirmation import ApplyConfirmationDialog
from .confirm_code import CodeConfirmationDialog
from .profile_create import ProfileCreateDialog
from .resume_select import ResumeSelectDialog

__all__ = [
    "ApplyConfirmationDialog",
    "CodeConfirmationDialog",
    "ProfileCreateDialog",
    "ResumeSelectDialog",
]
