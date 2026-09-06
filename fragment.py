# -*- coding: utf-8 -*-
"""Проверка ника на аукционе Fragment.

Без неё бот отдаёт ники вроде ajict, которые на t.me выглядят свободными,
а в настройках Telegram отвечает "this link is taken, but it's available
for purchase" - потому что ник выставлен на аукцион.
"""

import re
import threading
import time
import urllib.request

import config

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

LISTED = "listed"      # выставлен или продан - бесплатно не занять
ABSENT = "absent"      # на Fragment нет, значит можно брать
ERROR = "error"

_last_request = 0.0
_rate_lock = threading.Lock()


def _throttle():
    """Общий на все потоки лимит запросов."""
    global _last_request
    gap = 1.0 / max(config.RATE_LIMIT, 0.1)
    with _rate_lock:
        wait = gap - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.time()


def status(name):
    """LISTED / ABSENT / ERROR."""
    _throttle()
    req = urllib.request.Request("https://fragment.com/username/" + name,
                                 headers={"User-Agent": UA})
    try:
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    except Exception:
        return ERROR

    html = re.sub(r"(?s)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()

    # На странице ника идёт блок вида "<ник> .t.me <Статус> Subscribe..."
    found = re.search(re.escape(name) + r" \.t\.me (\w[\w ]*?) (?:Subscribe|Unsubscribe)",
                      text)
    if not found:
        return ABSENT

    label = found.group(1).strip().lower()
    if label.startswith(("available", "on auction", "taken", "sold")):
        return LISTED
    return ABSENT
