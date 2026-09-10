# -*- coding: utf-8 -*-
"""Подтверждение ника через сам Telegram.

t.me и Fragment молчат про внутренний резерв: страница пустая, на Fragment
ника нет, а при попытке занять выскакивает "username is invalid". Видит это
только MTProto - тот же протокол, по которому ходит обычный клиент.

Спрашиваем через contacts.ResolveUsername:
    USERNAME_NOT_OCCUPIED  - свободен по-настоящему
    USERNAME_INVALID       - Telegram держит у себя, занять не дадут
    успех                  - у ника есть владелец

Дёргаем редко и по одному: после пары десятков запросов подряд Telegram
просит подождать, а то и уводит метод в отказ на сутки. Поэтому сюда
попадают только те ники, что уже прошли t.me и Fragment - их единицы.
"""

import os
import threading
import time

SESSION = os.environ.get("TG_SESSION", "").strip()
API_ID = 33152316
API_HASH = "0f4ceed1ef9092455948e984fedca172"

# Пауза между запросами и то, насколько долго молчим, упёршись в лимит.
GAP = 0.9
FLOOD_COOLDOWN = 15 * 60

FREE = "free"
TAKEN = "taken"
RESERVED = "reserved"

_lock = threading.Lock()
_client = None
_last_call = 0.0
_flood_until = 0.0
_broken = False


def available():
    """Готовы ли мы вообще спрашивать Telegram."""
    return bool(SESSION) and not _broken and time.time() >= _flood_until


def _connect():
    global _client, _broken
    if _client is not None:
        return _client
    try:
        from telethon.sync import TelegramClient
        from telethon.sessions import StringSession
        client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
        client.connect()
        _client = client
    except Exception as e:
        # без сессии или без библиотеки просто работаем как раньше
        _broken = True
        raise e
    return _client


def confirm(name):
    """Вернуть FREE / TAKEN / RESERVED, либо None, если спросить не вышло."""
    global _last_call, _flood_until, _broken

    if not available():
        return None

    with _lock:
        wait = GAP - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()

        try:
            from telethon.tl.functions.contacts import ResolveUsernameRequest
            _connect()(ResolveUsernameRequest(name))
            return TAKEN
        except Exception as e:
            text = "%s: %s" % (type(e).__name__, e)
            if "UsernameNotOccupied" in text or "USERNAME_NOT_OCCUPIED" in text:
                return FREE
            if "UsernameInvalid" in text or "USERNAME_INVALID" in text:
                return RESERVED
            if "UsernamePurchaseAvailable" in text:
                return TAKEN
            if "FloodWait" in text or "flood" in text.lower():
                # переждём и вернёмся: без этого Telegram уводит метод
                # в отказ на часы, и проверка ляжет совсем
                _flood_until = time.time() + FLOOD_COOLDOWN
                return None
            return None
