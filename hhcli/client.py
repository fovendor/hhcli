import threading
import time
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import requests
import webview
from webview import WebViewException

from hhcli.database import (
    delete_profile,
    get_last_sync_timestamp,
    load_profile,
    log_http_metric,
    log_oauth_event,
    log_to_db,
    save_or_update_profile,
    set_last_sync_timestamp,
    upsert_negotiation_history,
)
from .constants import ApiErrorReason, LogSource
from .mimicry import (
    ANDROID_CLIENT_ID,
    ANDROID_CLIENT_SECRET,
    REDIRECT_URI,
    android_user_agent,
    sleep_human_delay,
)

API_BASE_URL = "https://api.hh.ru"
OAUTH_URL = "https://hh.ru/oauth"


class AuthorizationPending(RuntimeError):
    """Сигнализирует о необходимости повторной аутентификации."""


class HHApiClient:
    """Клиент для API hh.ru, мимикрирующий под Android-приложение."""

    RETRY_ATTEMPTS = 3
    RETRY_BACKOFF_SECONDS = 1.0
    MIN_DELAY = 0.3
    MAX_DELAY = 1.0

    def __init__(self):
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.token_expires_at: datetime | None = None
        self.profile_name: str | None = None
        self._auth_lock = threading.Lock()
        self._auth_in_progress = False
        self._last_auth_url: str | None = None
        self._last_request_ts = time.monotonic()

        self.session = requests.Session()
        self.session.headers.update(
            {
                "user-agent": android_user_agent(),
                "x-hh-app-active": "true",
            }
        )

    def load_profile_data(self, profile_name: str):
        profile_data = load_profile(profile_name)
        if not profile_data:
            raise ValueError(f"Профиль '{profile_name}' не найден.")
        self.profile_name = profile_data["profile_name"]
        self.access_token = profile_data["access_token"]
        self.refresh_token = profile_data["refresh_token"]
        self.token_expires_at = profile_data["expires_at"]

    def is_authenticated(self) -> bool:
        return bool(self.access_token) and bool(self.token_expires_at) and (
            self.token_expires_at > datetime.now()
        )

    def start_authorization_flow(self, *, reason: str | None = None) -> None:
        """Запускает авторизацию через pywebview (только из главного потока)."""
        if not self.profile_name:
            raise AuthorizationPending(
                "Профиль не загружен, авторизация невозможна."
            )

        with self._auth_lock:
            if self._auth_in_progress:
                log_to_db(
                    "INFO",
                    LogSource.OAUTH,
                    f"Повторный запрос авторизации для профиля '{self.profile_name}'.",
                )
                return
            self._auth_in_progress = True

        log_details = f"Причина: {reason}" if reason else "Причина не указана."
        log_to_db(
            "INFO",
            LogSource.OAUTH,
            f"Запускаю авторизацию через pywebview для '{self.profile_name}'. {log_details}",
        )
        try:
            success = self.authorize(self.profile_name)
            if success:
                log_to_db(
                    "INFO",
                    LogSource.OAUTH,
                    f"Авторизация профиля '{self.profile_name}' завершена.",
                )
            else:
                log_to_db(
                    "ERROR",
                    LogSource.OAUTH,
                    f"Авторизация профиля '{self.profile_name}' завершилась с ошибкой.",
                )
        except WebViewException as exc:
            msg = (
                "pywebview не смог инициализировать GUI. "
                "Установите GTK+WebKit или Qt с Python-расширениями. "
                "Например, в Ubuntu 24.04: "
                "`sudo apt install python3-gi gir1.2-webkit2-4.1 "
                "gir1.2-gtk-3.0 libwebkit2gtk-4.1-0`."
            )
            log_to_db("ERROR", LogSource.OAUTH, f"{msg} Детали: {exc}")
            raise RuntimeError(msg) from exc
        except Exception as exc:  # noqa: BLE001
            log_to_db(
                "ERROR",
                LogSource.OAUTH,
                f"Исключение внутри авторизации профиля '{self.profile_name}': {exc}",
            )
            raise
        finally:
            with self._auth_lock:
                self._auth_in_progress = False

    def ensure_active_token(self) -> None:
        """Проверяет токен и при необходимости инициирует повторную авторизацию."""
        if self.is_authenticated():
            return
        try:
            self._refresh_token()
        except AuthorizationPending:
            raise
        except Exception as exc:  # noqa: BLE001
            log_to_db(
                "ERROR",
                LogSource.API_CLIENT,
                f"Не удалось обновить токен для '{self.profile_name}': {exc}",
            )
            self.start_authorization_flow(reason="refresh_failed")
            raise AuthorizationPending(
                "Срок действия токена истёк. Открыто окно авторизации."
            ) from exc

    def _save_token(self, token_data: dict, user_info: dict):
        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        save_or_update_profile(
            self.profile_name, user_info, token_data, expires_at
        )
        self.access_token = token_data["access_token"]
        self.refresh_token = token_data["refresh_token"]
        self.token_expires_at = expires_at

    def _refresh_token(self):
        if not self.refresh_token:
            msg = (
                f"Нет refresh_token для обновления профиля '{self.profile_name}'. "
                "Запускаю переавторизацию."
            )
            log_to_db("ERROR", LogSource.API_CLIENT, msg)
            self.start_authorization_flow(reason="missing_refresh_token")
            raise AuthorizationPending(
                "Не найден refresh_token. Открыта страница авторизации."
            )
        log_to_db(
            "INFO",
            LogSource.API_CLIENT,
            f"Токен для профиля '{self.profile_name}' истек, обновляю...",
        )
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": ANDROID_CLIENT_ID,
            "client_secret": ANDROID_CLIENT_SECRET,
        }
        self._last_request_ts = sleep_human_delay(self._last_request_ts)
        started = time.monotonic()
        response = self.session.post(f"{OAUTH_URL}/token", data=payload)
        log_http_metric(
            "POST",
            "/oauth/token",
            getattr(response, "status_code", None),
            int((time.monotonic() - started) * 1000),
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as e:  # noqa: PERF203
            log_to_db(
                "ERROR",
                LogSource.API_CLIENT,
                f"Ошибка обновления токена: {e.response.text if e.response else e}",
            )
            error_details: dict[str, Any] = {}
            try:
                error_details = e.response.json() if e.response else {}
            except Exception:  # noqa: BLE001
                pass
            if (
                e.response
                and e.response.status_code in (400, 401)
                and error_details.get("error") == "invalid_grant"
            ):
                log_oauth_event(self.profile_name, "refresh_failed", "invalid_grant")
                self.start_authorization_flow(reason="invalid_grant")
                raise AuthorizationPending(
                    "Не удалось обновить токен. "
                    "Откройте окно авторизации."
                ) from e
            raise
        new_token_data = response.json()
        user_info = load_profile(self.profile_name)
        self._save_token(new_token_data, user_info)
        log_to_db("INFO", LogSource.API_CLIENT, "Токен успешно обновлен.")
        log_oauth_event(self.profile_name, "refresh_success")

    def authorize(self, profile_name: str) -> bool:
        """Полный OAuth-поток через pywebview с мобильными кредами."""
        self.profile_name = profile_name

        auth_url = (
            f"{OAUTH_URL}/authorize?response_type=code"
            f"&client_id={ANDROID_CLIENT_ID}"
            f"&redirect_uri={REDIRECT_URI}"
        )
        self._last_auth_url = auth_url
        log_oauth_event(self.profile_name, "start_auth", auth_url)
        code_holder: dict[str, str] = {}
        event = threading.Event()

        def handle_loaded(*_args):
            if event.is_set():
                return
            try:
                current_url = window.get_current_url() or ""
            except Exception:
                return
            if not current_url.startswith(REDIRECT_URI):
                return
            parsed = urlsplit(current_url)
            code = parse_qs(parsed.query).get("code", [None])[0]
            if not code:
                return
            code_holder["code"] = code
            event.set()
            log_oauth_event(self.profile_name, "code_received")
            try:
                window.destroy()
            except Exception:
                pass

        window = webview.create_window(
            "Авторизация hh.ru",
            url=auth_url,
            width=480,
            height=800,
            resizable=True,
        )
        window.events.loaded += handle_loaded

        def watch_redirect():
            while not event.is_set():
                try:
                    current_url = window.get_current_url() or ""
                except Exception:
                    break
                if current_url.startswith(REDIRECT_URI):
                    handle_loaded()
                    break
                time.sleep(0.2)

        webview.start(func=watch_redirect, debug=False)

        if not event.is_set():
            log_to_db(
                "ERROR",
                LogSource.OAUTH,
                f"Код авторизации не получен для профиля '{profile_name}'.",
            )
            log_oauth_event(self.profile_name, "auth_failed", "no_code")
            return False

        payload = {
            "grant_type": "authorization_code",
            "code": code_holder["code"],
            "client_id": ANDROID_CLIENT_ID,
            "client_secret": ANDROID_CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
        }

        self._last_request_ts = sleep_human_delay(self._last_request_ts)
        started = time.monotonic()
        response = self.session.post(f"{OAUTH_URL}/token", data=payload)
        log_http_metric(
            "POST",
            "/oauth/token",
            getattr(response, "status_code", None),
            int((time.monotonic() - started) * 1000),
        )
        response.raise_for_status()
        token_data = response.json()

        headers = {"Authorization": f"Bearer {token_data['access_token']}"}
        self._last_request_ts = sleep_human_delay(self._last_request_ts)
        started = time.monotonic()
        user_info_resp = self.session.get(f"{API_BASE_URL}/me", headers=headers)
        log_http_metric(
            "GET",
            "/me",
            getattr(user_info_resp, "status_code", None),
            int((time.monotonic() - started) * 1000),
        )
        user_info_resp.raise_for_status()

        self._save_token(token_data, user_info_resp.json())
        log_oauth_event(self.profile_name, "auth_success")
        return True

    def _request(self, method: str, endpoint: str, **kwargs):
        try:
            self.ensure_active_token()
        except AuthorizationPending as pending:
            log_to_db("ERROR", LogSource.API_CLIENT, str(pending))
            raise

        headers = kwargs.setdefault("headers", {})
        headers["Authorization"] = f"Bearer {self.access_token}"
        url = f"{API_BASE_URL}{endpoint}"
        attempt = 0
        while True:
            self._last_request_ts = sleep_human_delay(self._last_request_ts)
            try:
                started = time.monotonic()
                response = self.session.request(method, url, **kwargs)
                log_http_metric(
                    method,
                    endpoint,
                    getattr(response, "status_code", None),
                    int((time.monotonic() - started) * 1000),
                )
                response.raise_for_status()
                if response.status_code in (201, 204):
                    return None
                return response.json()
            except requests.HTTPError as e:
                if e.response and e.response.status_code == 401:
                    log_to_db(
                        "WARN",
                        LogSource.API_CLIENT,
                        f"Получен 401 Unauthorized для {endpoint}. "
                        "Повторная попытка после обновления токена.",
                    )
                    try:
                        self.ensure_active_token()
                        headers["Authorization"] = f"Bearer {self.access_token}"
                        self._last_request_ts = sleep_human_delay(
                            self._last_request_ts
                        )
                        started = time.monotonic()
                        response = self.session.request(method, url, **kwargs)
                        log_http_metric(
                            method,
                            endpoint,
                            getattr(response, "status_code", None),
                            int((time.monotonic() - started) * 1000),
                        )
                        response.raise_for_status()
                        if response.status_code in (201, 204):
                            return None
                        return response.json()
                    except AuthorizationPending:
                        raise
                    except Exception as refresh_e:  # noqa: BLE001
                        msg = (
                            "Повторная попытка обновления токена не удалась. "
                            f"Ошибка: {refresh_e}"
                        )
                        log_to_db("ERROR", LogSource.API_CLIENT, msg)
                        raise ConnectionError(
                            "Не удалось обновить токен. "
                            "Попробуйте пере-авторизоваться."
                        ) from refresh_e
                log_to_db(
                    "ERROR",
                    LogSource.API_CLIENT,
                    f"HTTP ошибка для {method} {endpoint}: "
                    f"{e.response.status_code if e.response else 'n/a'} {e.response.text if e.response else ''}",
                )
                raise e
            except requests.RequestException as e:
                log_http_metric(method, endpoint, None, 0)
                attempt += 1
                if attempt > self.RETRY_ATTEMPTS:
                    msg = (
                        "Ошибка соединения с hh.ru. "
                        "Проверьте подключение или повторите попытку позже."
                    )
                    log_to_db("ERROR", LogSource.API_CLIENT, f"{msg} Детали: {e}")
                    raise ConnectionError(msg) from e
                delay = self.RETRY_BACKOFF_SECONDS * attempt
                log_to_db(
                    "WARN",
                    LogSource.API_CLIENT,
                    f"Сетевая ошибка для {method} {endpoint} (попытка "
                    f"{attempt}/{self.RETRY_ATTEMPTS}). Повтор через {delay:.1f}с. "
                    f"Детали: {e}",
                )
                time.sleep(delay)

    def get_my_resumes(self):
        return self._request("GET", "/resumes/mine")

    def get_similar_vacancies(
        self, resume_id: str, page: int = 0, per_page: int = 50
    ):
        params = {"page": page, "per_page": per_page}
        data = self._request(
            "GET", f"/resumes/{resume_id}/similar_vacancies", params=params
        )
        data.setdefault("pages", data.get("found", 0) // per_page + 1)
        return data

    def search_vacancies(self, config: dict, page: int = 0, per_page: int = 50):
        """Выполняет поиск вакансий по конфигурации профиля и возвращает ответ API."""
        positive_keywords = config.get("text_include", [])
        positive_str = " OR ".join(f'"{kw}"' for kw in positive_keywords)

        negative_keywords = config.get("negative", [])
        negative_str = " OR ".join(f'"{kw}"' for kw in negative_keywords)

        text_query = ""
        if positive_str:
            text_query = f"({positive_str})"

        if negative_str:
            if text_query:
                text_query += f" NOT ({negative_str})"
            else:
                text_query = f"NOT ({negative_str})"

        params = {
            "text": text_query,
            "area": config.get("area_id"),
            "professional_role": config.get("role_ids_config", []),
            "search_field": config.get("search_field"),
            "period": config.get("period"),
            "order_by": "publication_time",
            "page": page,
            "per_page": per_page,
        }

        if config.get("work_format") and config["work_format"] != "ANY":
            params["work_format"] = config["work_format"]

        params = {k: v for k, v in params.items() if v}

        return self._request("GET", "/vacancies", params=params)

    def get_vacancy_details(self, vacancy_id: str):
        return self._request("GET", f"/vacancies/{vacancy_id}")

    def get_dictionaries(self):
        """Запрашивает общие справочники hh.ru."""
        log_to_db("INFO", LogSource.API_CLIENT, "Запрос общих справочников...")
        return self._request("GET", "/dictionaries")

    def get_areas(self):
        """Запрашивает полный список регионов hh.ru."""
        log_to_db("INFO", LogSource.API_CLIENT, "Запрос справочника регионов...")
        return self._request("GET", "/areas")

    def get_professional_roles(self):
        """Запрашивает справочник профессиональных ролей hh.ru."""
        log_to_db(
            "INFO", LogSource.API_CLIENT, "Запрос справочника профессиональных ролей..."
        )
        return self._request("GET", "/professional_roles")

    def sync_negotiation_history(self):
        log_to_db(
            "INFO",
            LogSource.SYNC_ENGINE,
            f"Запуск синхронизации истории откликов "
            f"для профиля '{self.profile_name}'.",
        )
        last_sync = get_last_sync_timestamp(self.profile_name)
        params = {"order_by": "updated_at", "per_page": 100}
        if last_sync:
            params["date_from"] = last_sync.isoformat()
            log_to_db(
                "INFO",
                LogSource.SYNC_ENGINE,
                f"Найдена последняя синхронизация: {last_sync}. "
                f"Загружаем обновления.",
            )
        all_items = []
        page = 0
        while True:
            params["page"] = page
            try:
                log_to_db(
                    "INFO",
                    LogSource.SYNC_ENGINE,
                    f"Запрос страницы {page} истории откликов...",
                )
                data = self._request("GET", "/negotiations", params=params)
                items = data.get("items", [])
                all_items.extend(items)
                if page >= data.get("pages", 0) - 1:
                    break
                page += 1
            except requests.HTTPError as e:
                log_to_db(
                    "ERROR",
                    LogSource.SYNC_ENGINE,
                    f"Ошибка при загрузке истории откликов: {e}",
                )
                return
        if all_items:
            log_to_db(
                "INFO",
                LogSource.SYNC_ENGINE,
                f"Получено {len(all_items)} обновленных записей. "
                f"Сохранение в БД...",
            )
            upsert_negotiation_history(all_items, self.profile_name)
            log_to_db("INFO", LogSource.SYNC_ENGINE, "Сохранение завершено.")
        else:
            log_to_db(
                "INFO",
                LogSource.SYNC_ENGINE,
                "Новых обновлений в истории откликов не найдено.",
            )
        set_last_sync_timestamp(self.profile_name, datetime.now())
        log_to_db("INFO", LogSource.SYNC_ENGINE, "Синхронизация успешно завершена.")

    def apply_to_vacancy(
        self, resume_id: str, vacancy_id: str, message: str = ""
    ) -> tuple[bool, str]:
        payload = {
            "resume_id": resume_id,
            "vacancy_id": vacancy_id,
            "message": message,
        }
        try:
            self._request("POST", "/negotiations", data=payload)
            log_to_db(
                "INFO",
                LogSource.API_CLIENT,
                f"Успешный отклик на вакансию {vacancy_id} "
                f"с резюме {resume_id}.",
            )
            return True, ApiErrorReason.APPLIED
        except requests.HTTPError as e:
            reason = ApiErrorReason.UNKNOWN_API_ERROR
            try:
                error_data = e.response.json()
                if "errors" in error_data and error_data["errors"]:
                    first_error = error_data["errors"][0]
                    reason = first_error.get("value", first_error.get("type"))
                elif "description" in error_data:
                    reason = error_data["description"]
            except Exception:  # noqa: BLE001
                reason = f"http_{e.response.status_code}"

            log_to_db(
                "WARN",
                LogSource.API_CLIENT,
                f"API отклонил отклик на {vacancy_id}. "
                f"Причина: {reason}. Детали: {e.response.text if e.response else e}",
            )
            return False, reason
        except requests.RequestException as e:
            log_to_db(
                "ERROR",
                LogSource.API_CLIENT,
                f"Сетевая ошибка при отклике на {vacancy_id}: {e}",
            )
            return False, ApiErrorReason.NETWORK_ERROR

    def get_negotiation(self, negotiation_id: str):
        """Возвращает подробную информацию об отклике/приглашении."""
        return self._request("GET", f"/negotiations/{negotiation_id}")

    def get_negotiation_messages(
        self,
        negotiation_id: str,
        *,
        page: int = 0,
        per_page: int = 50,
        with_text_only: bool = False,
    ) -> dict:
        """Получает сообщения по отклику (для переписки в TUI)."""
        params = {
            "page": page,
            "per_page": per_page,
            "with_text_only": str(bool(with_text_only)).lower(),
        }
        return self._request(
            "GET",
            f"/negotiations/{negotiation_id}/messages",
            params=params,
        )

    def get_messages(self, negotiation_id: str):
        """Возвращает переписку по отклику."""
        return self._request("GET", f"/negotiations/{negotiation_id}/messages")

    def send_message(
        self, negotiation_id: str, message: str, save_to_db: bool = True
    ) -> tuple[bool, str]:
        payload = {"message": message}
        try:
            self._request(
                "POST",
                f"/negotiations/{negotiation_id}/messages",
                json=payload,
            )
            if save_to_db:
                upsert_negotiation_history([], self.profile_name)
            log_to_db(
                "INFO",
                LogSource.API_CLIENT,
                f"Сообщение по отклику {negotiation_id} отправлено.",
            )
            return True, "sent"
        except requests.HTTPError as e:
            try:
                error_data = e.response.json()
                reason = error_data.get("description") or error_data.get("errors")
            except Exception:  # noqa: BLE001
                reason = f"http_{e.response.status_code}"
            log_to_db(
                "WARN",
                LogSource.API_CLIENT,
                f"Не удалось отправить сообщение по отклику {negotiation_id}. "
                f"Причина: {reason}.",
            )
            return False, str(reason)
        except requests.RequestException as e:
            log_to_db(
                "ERROR",
                LogSource.API_CLIENT,
                f"Сетевая ошибка при отправке сообщения по {negotiation_id}: {e}",
            )
            return False, ApiErrorReason.NETWORK_ERROR

    def delete_profile(self, profile_name: str):
        delete_profile(profile_name)
