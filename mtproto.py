# -*- coding: utf-8 -*-
"""Подтверждение ника через сам Telegram.

t.me и Fragment молчат про внутренний резерв: страница пустая, на Fragment
ника нет, а при попытке занять выскакивает "username is invalid". Видит это
только MTProto - тот же протокол, по которому ходит обычный клиент.

Спрашивать напрямую отсюда мы не можем: для MTProto нужна строка сессии,
то есть полный доступ к аккаунту. Она уже лежит в Supabase, у соседнего
бота, поэтому спрашиваем его - ключ никуда не переезжает.

Дёргаем редко и только тех, кто уже прошёл t.me и Fragment: у метода
жёсткие лимиты, после пары десятков запросов Telegram просит подождать.
"""

import json
import os
import threading
import time
import urllib.error
import urllib.request

SESSION = os.environ.get("TG_SESSION", "").strip()
API_ID = 33152316
API_HASH = "0f4ceed1ef9092455948e984fedca172"

ENDPOINT = os.environ.get(
    "CONFIRM_URL",
    "https://ubtbjowghezwhevpawwd.supabase.co/functions/v1/username-bot")
TOKEN = os.environ.get("CONFIRM_SECRET", "a0d3240a7228850d359116050e382b0e")

# Пауза между запросами и то, насколько долго молчим после отказа.
GAP = 0.5
COOLDOWN = 5 * 60

FREE = "free"
TAKEN = "taken"
RESERVED = "reserved"

_lock = threading.Lock()
_last_call = 0.0
_silent_until = 0.0


def available():
    """Готовы ли мы спрашивать про резерв прямо сейчас."""
    return (bool(SESSION) or bool(ENDPOINT)) and time.time() >= _silent_until


_client = None


def _via_telethon(name):
    """Спросить самим - нужна строка сессии в TG_SESSION."""
    global _client, _silent_until
    try:
        if _client is None:
            from telethon.sync import TelegramClient
            from telethon.sessions import StringSession
            _client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
            _client.connect()
        from telethon.tl.functions.contacts import ResolveUsernameRequest
        _client(ResolveUsernameRequest(name))
        return TAKEN
    except Exception as e:
        text = "%s: %s" % (type(e).__name__, e)
        if "UsernameNotOccupied" in text:
            return FREE
        if "UsernameInvalid" in text:
            return RESERVED
        if "UsernamePurchaseAvailable" in text:
            return TAKEN
        if "FloodWait" in text:
            # Telegram просит подождать: молчим, иначе метод уведут в
            # отказ на часы и проверка ляжет совсем
            _silent_until = time.time() + COOLDOWN
        return None


def confirm(name):
    """Вернуть FREE / TAKEN / RESERVED, либо None, если спросить не вышло."""
    global _last_call, _silent_until

    if not available():
        return None

    with _lock:
        wait = GAP - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()

    if SESSION:
        return _via_telethon(name)

    body = json.dumps({"confirm": name}).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT, data=body,
        headers={"Content-Type": "application/json",
                 "x-telegram-bot-api-secret-token": TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status = json.loads(r.read().decode()).get("status")
    except Exception:
        # не дозвонились - переждём, чтобы не долбить впустую весь поиск
        _silent_until = time.time() + COOLDOWN
        return None

    if status in (FREE, TAKEN, RESERVED):
        return status
    return None
