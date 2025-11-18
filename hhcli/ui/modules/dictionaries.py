from __future__ import annotations

from typing import Callable

from ...client import AuthorizationPending
from ...constants import LogSource
from ...database import (
    get_dictionary_from_cache,
    log_to_db,
    save_dictionary_to_cache,
)
from ...reference_data import ensure_reference_data

NotifyFn = Callable[..., None]


def cache_dictionaries(
    client,
    *,
    notify: NotifyFn | None = None,
) -> dict:
    """Загружает словари hh.ru и обновляет справочные данные"""
    dictionaries: dict = {}
    cached_dicts = get_dictionary_from_cache("main_dictionaries")
    if cached_dicts:
        log_to_db("INFO", LogSource.TUI, "Справочники загружены из кэша.")
        dictionaries = cached_dicts
    else:
        log_to_db(
            "INFO",
            LogSource.TUI,
            "Кэш справочников пуст/устарел. Запрос к API...",
        )
        try:
            live_dicts = client.get_dictionaries()
            save_dictionary_to_cache("main_dictionaries", live_dicts)
            dictionaries = live_dicts
            log_to_db("INFO", LogSource.TUI, "Справочники успешно закэшированы.")
        except AuthorizationPending as auth_exc:
            log_to_db(
                "WARN",
                LogSource.TUI,
                f"Не удалось загрузить справочники: {auth_exc}",
            )
            if notify:
                notify(
                    "Завершите авторизацию, чтобы обновить справочники.",
                    title="Авторизация",
                    severity="warning",
                    timeout=4,
                )
            return dictionaries
        except Exception as exc:  # pragma: no cover - сетевые ошибки
            log_to_db(
                "ERROR",
                LogSource.TUI,
                f"Не удалось загрузить справочники: {exc}",
            )
            if notify:
                notify("Ошибка загрузки справочников!", severity="error")
            return dictionaries

    try:
        updates = ensure_reference_data(client)
        if updates.get("areas"):
            log_to_db("INFO", LogSource.TUI, "Справочник регионов обновлён.")
        if updates.get("professional_roles"):
            log_to_db(
                "INFO",
                LogSource.TUI,
                "Справочник профессиональных ролей обновлён.",
            )
    except AuthorizationPending as auth_exc:
        log_to_db(
            "WARN",
            LogSource.TUI,
            f"Обновление справочников остановлено до завершения авторизации: {auth_exc}",
        )
    except Exception as exc:  # pragma: no cover - сетевые ошибки
        log_to_db(
            "ERROR",
            LogSource.TUI,
            f"Не удалось обновить справочники регионов/ролей: {exc}",
        )

    return dictionaries


__all__ = ["cache_dictionaries"]
