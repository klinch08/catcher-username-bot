# -*- coding: utf-8 -*-
"""Подтверждение ника через сам Telegram.

t.me и Fragment молчат про внутренний резерв: страница пустая, на Fragment
ника нет, а при попытке занять выскакивает "username is invalid". Видит это
только MTProto, и только account.CheckUsername - тот же вызов, что делает
приложение, когда вводишь ник в настройках. contacts.ResolveUsername для
этого не годится: jemag и ovyvo он называет свободными, хотя занять их не дают.

Все обращения к Telegram идут через один выделенный поток. Клиент Telethon
привязан к циклу событий того потока, где создан, и из чужого потока вызов
падает. Раньше клиента дёргали из пула проверки, ошибка глоталась, и
зарезервированные ники уходили в выдачу как свободные.

Если TG_SESSION не задан, спрашиваем соседнего бота, у которого сессия есть.
"""

import asyncio
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SESSION = os.environ.get("TG_SESSION", "").strip()
API_ID = 33152316
API_HASH = "0f4ceed1ef9092455948e984fedca172"

ENDPOINT = os.environ.get(
    "CONFIRM_URL",
    "https://ubtbjowghezwhevpawwd.supabase.co/functions/v1/username-bot")
TOKEN = os.environ.get("CONFIRM_SECRET", "a0d3240a7228850d359116050e382b0e")

# CheckUsername строже всех по лимитам: частые запросы Telegram однажды
# наказал отказом на 23 часа, поэтому не чаще раза в секунду.
GAP = 1.0
COOLDOWN = 5 * 60

FREE = "free"
TAKEN = "taken"
RESERVED = "reserved"

def _own_loop():
    # Python 3.14 больше не создаёт цикл событий в потоке сам, а Telethon
    # без него падает с "There is no current event loop" на первом же вызове
    asyncio.set_event_loop(asyncio.new_event_loop())


# один поток на всё общение с Telegram - и клиент живёт в нём же
_telegram = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mtproto",
                               initializer=_own_loop)
_client = None
_last_call = 0.0
_silent_until = 0.0


def _log(*parts):
    print(time.strftime("%H:%M:%S ") + "mtproto: " + " ".join(str(p) for p in parts),
          flush=True)


def available():
    """Можно ли прямо сейчас подтвердить ник через Telegram."""
    return (bool(SESSION) or bool(ENDPOINT)) and time.time() >= _silent_until


def _back_off(seconds, reason):
    global _silent_until
    _silent_until = time.time() + seconds
    _log("пауза %d с: %s" % (seconds, reason))


def _ask_telegram(name):
    """Выполняется только в потоке _telegram."""
    global _client, _last_call

    wait = GAP - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()

    try:
        if _client is None:
            from telethon.sync import TelegramClient
            from telethon.sessions import StringSession
            _client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
            _client.connect()
        from telethon.tl.functions.account import CheckUsernameRequest
        return FREE if _client(CheckUsernameRequest(name)) else TAKEN
    except Exception as e:
        kind = type(e).__name__
        if "UsernameInvalid" in kind:
            return RESERVED
        if "UsernamePurchaseAvailable" in kind or "UsernameOccupied" in kind:
            return TAKEN
        if "FloodWait" in kind:
            # переждём ровно столько, сколько просит Telegram: полезем
            # раньше - и он уведёт метод в отказ на часы
            _back_off(max(COOLDOWN, getattr(e, "seconds", 0)), kind)
        else:
            # неизвестная ошибка: молча пропустить ник как свободный нельзя,
            # поэтому говорим о ней и честно предупреждаем в выдаче
            _log("не смог проверить %s: %s %s" % (name, kind, e))
            _back_off(60, kind)
        return None


def _ask_neighbour(name):
    body = json.dumps({"confirm": name}).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT, data=body,
        headers={"Content-Type": "application/json",
                 "x-telegram-bot-api-secret-token": TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status = json.loads(r.read().decode()).get("status")
    except Exception as e:
        _back_off(COOLDOWN, "сосед не ответил: %s" % type(e).__name__)
        return None
    return status if status in (FREE, TAKEN, RESERVED) else None


def confirm(name):
    """Вернуть FREE / TAKEN / RESERVED, либо None, если спросить не вышло."""
    if not available():
        return None
    if SESSION:
        # ждём ответа из потока Telegram; очередь там же и выстраивается
        return _telegram.submit(_ask_telegram, name).result()
    return _ask_neighbour(name)
