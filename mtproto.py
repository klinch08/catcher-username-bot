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
    return bool(ENDPOINT) and time.time() >= _silent_until


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
