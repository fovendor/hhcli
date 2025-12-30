import sys

from hhcli.client import HHApiClient
from hhcli.database import (
    cleanup_app_logs,
    cleanup_vacancy_cache,
    get_active_profile_name,
    get_db_info,
    init_db,
    log_to_db,
    set_active_profile,
)
from hhcli.ui.tui import HHCliApp
from hhcli.version import get_version

def run():
    """Точка входа, которая запускает интерфейс и разбирает аргументы командной строки"""
    args = sys.argv[1:]

    if any(flag in args for flag in ("-v", "--version")):
        print(get_version())
        return

    if any(flag in args for flag in ("--info", "-i")):
        init_db()
        info = get_db_info()
        print("hhcli информация:")
        print(f"  Версия: {get_version()}")
        print(f"  База данных: {info['db_path']}")
        print(f"  Активный профиль: {info['active_profile'] or 'не выбран'}")
        print(f"  Число профилей: {info['profile_count']}")
        if info["profiles"]:
            print(f"  Профили: {', '.join(info['profiles'])}")
        return

    init_db()
    cache_purged = cleanup_vacancy_cache()
    logs_purged = cleanup_app_logs()
    if cache_purged or logs_purged:
        log_to_db(
            "INFO",
            "Main",
            f"Очистка БД при запуске: кэш вакансий (-{cache_purged}), логи (-{logs_purged}).",
        )

    log_to_db("INFO", "Main", "Запуск приложения hhcli.")

    active_profile = get_active_profile_name()

    client = HHApiClient()
    if active_profile:
        try:
            log_to_db("INFO", "Main", f"Профиль '{active_profile}' активен. Загрузка данных профиля.")
            client.load_profile_data(active_profile)
        except ValueError as e:
            log_to_db("ERROR", "Main", f"Ошибка загрузки профиля '{active_profile}': {e}")
            print(f"Ошибка: {e}")
            return
    else:
        log_to_db("INFO", "Main", "Активный профиль не найден. Перехожу в TUI для выбора/создания.")

    app = HHCliApp(client=client)
    app.apply_theme_from_profile(active_profile)

    log_to_db("INFO", "Main", "Запуск TUI.")
    result = app.run()

    if result:
        log_to_db("ERROR", "Main", f"TUI завершился с ошибкой: {result}")
        print(f"\n[ОШИБКА] {result}")

    log_to_db("INFO", "Main", "Приложение hhcli завершило работу.")

if __name__ == "__main__":
    run()
