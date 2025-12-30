import random
import time
import uuid

ANDROID_CLIENT_ID = "HIOMIAS39CA9DICTA7JIO64LQKQJF5AGIK74G9ITJKLNEDAOH5FHS5G1JI7FOEGD"
ANDROID_CLIENT_SECRET = (
    "V9M870DE342BGHFRUJ5FTCGCUA1482AN0DI8C5TFI9ULMA89H10N60NOP8I4JMVS"
)
REDIRECT_URI = "hhandroid://oauthresponse"


def android_user_agent() -> str:
    """Генерирует правдоподобный UA официального Android-клиента hh.ru."""
    devices = (
        "23053RN02A",
        "23053RN02Y",
        "23053RN02I",
        "23053RN02L",
        "23077RABDC",
    )
    device = random.choice(devices)
    minor = random.randint(100, 150)
    patch = random.randint(10000, 15000)
    android = random.randint(11, 15)
    return (
        f"ru.hh.android/7.{minor}.{patch}, Device: {device}, "
        f"Android OS: {android} (UUID: {uuid.uuid4()})"
    )


def sleep_human_delay(
    last_request_time: float, *, min_delay: float = 0.3, max_delay: float = 1.0
) -> float:
    """Рандомизирует паузу между запросами для обхода ddos-guard."""
    target_delay = random.uniform(min_delay, max_delay)
    elapsed = time.monotonic() - last_request_time
    wait_for = max(0.0, target_delay - elapsed)
    if wait_for:
        time.sleep(wait_for)
    return time.monotonic()
