# -*- coding: utf-8 -*-
"""Проверка занятости ника по публичной странице t.me."""

import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import config
import fragment

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

FREE = "free"
TAKEN = "taken"
RESERVED = "reserved"
ERROR = "error"

# Кто держит ник (для TAKEN).
USER = "user"
BOT = "bot"
CHANNEL = "channel"
GROUP = "group"
AUCTION = "auction"

KIND_TITLES = {
    USER: "пользователь",
    BOT: "бот",
    CHANNEL: "канал",
    GROUP: "группа",
    AUCTION: "аукцион Fragment",
}

# Служебные пути и слова, которые Telegram держит за собой.
# Страница t.me у них пустая, поэтому выглядят "свободными", но занять нельзя.
RESERVED_NAMES = {
    "admin", "administrator", "telegram", "support", "security", "settings",
    "contact", "contacts", "about", "help", "faq", "blog", "apps", "auth",
    "login", "start", "share", "widget", "iv", "img", "js", "css", "api",
    "bot", "bots", "channel", "channels", "group", "groups", "chat", "chats",
    "joinchat", "addstickers", "addemoji", "addtheme", "addlist", "proxy",
    "socks", "setlanguage", "confirmphone", "premium", "giftcode", "invoice",
    "wallet", "fragment", "username", "usernames", "me", "web", "desktop",
    "android", "ios", "macos", "windows", "linux", "download", "press",
    "privacy", "terms", "tos", "jobs", "moderation", "abuse", "spam",
    "notoscam", "stickers", "themes", "gifs", "video", "photo", "file",
}

_last_request = 0.0
_rate_lock = threading.Lock()


def _throttle():
    """Общий на все потоки лимит: не больше config.RATE_LIMIT запросов в секунду."""
    global _last_request
    gap = 1.0 / max(config.RATE_LIMIT, 0.1)
    with _rate_lock:
        wait = gap - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.time()


def _kind(html, name):
    """Определить, что именно занимает ник."""
    extra = re.search(r'tgme_page_extra["\'][^>]*>([^<]*)', html)
    extra = extra.group(1).strip().lower() if extra else ""
    if "subscriber" in extra or "подписчик" in extra:
        return CHANNEL
    if "member" in extra or "online" in extra or "участник" in extra:
        return GROUP
    if name.lower().endswith("bot"):
        return BOT
    return USER


def check(name):
    """Вернуть (статус, кто_занимает).

    статус: FREE / TAKEN / RESERVED / ERROR
    кто_занимает: USER / BOT / CHANNEL / GROUP или None

    """
    name = name.lower()
    if name in RESERVED_NAMES:
        return RESERVED, None

    _throttle()
    req = urllib.request.Request("https://t.me/" + name, headers={"User-Agent": UA})
    try:
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return (FREE, None) if e.code == 404 else (ERROR, None)
    except Exception:
        return ERROR, None

    # У занятого ника страница содержит карточку профиля/канала.
    if "tgme_page_title" in html:
        return TAKEN, _kind(html, name)

    # Пустая страница t.me ещё не значит "свободен": ник может стоять
    # на аукционе Fragment, и тогда Telegram его бесплатно не отдаст.
    if fragment.status(name) == fragment.LISTED:
        return TAKEN, AUCTION

    return FREE, None


def describe(status, kind):
    """Человеческая подпись к результату."""
    if status == FREE:
        return "✅ свободен"
    if status == RESERVED:
        return "\U0001F512 зарезервирован Telegram"
    if status == TAKEN:
        return "❌ занят (%s)" % KIND_TITLES.get(kind, "кто-то")
    return "❓ не удалось проверить"


def check_many(name_list):
    """Проверить пачку ников параллельно. Возвращает [(ник, статус, kind)]."""
    with ThreadPoolExecutor(max_workers=config.WORKERS) as pool:
        results = list(pool.map(lambda n: (n,) + check(n), name_list))
    return results
