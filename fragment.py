# -*- coding: utf-8 -*-
"""Проверка ника на аукционе Fragment.

Без неё бот отдаёт ники вроде ajict, которые на t.me выглядят свободными,
а в настройках Telegram отвечает "this link is taken, but it's available
for purchase" - потому что ник выставлен на аукцион.
"""

import re
import time
import urllib.request

import config
import ratelimit

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

LISTED = "listed"      # выставлен или продан - бесплатно не занять
ABSENT = "absent"      # на Fragment нет, значит можно брать
ERROR = "error"

_limiter = ratelimit.Limiter(config.FRAGMENT_RATE)


def _fetch(name):
    _limiter.acquire()
    req = urllib.request.Request("https://fragment.com/username/" + name,
                                 headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")


def status(name):
    """LISTED / ABSENT / ERROR.

    Одна повторная попытка: Fragment под нагрузкой иногда обрывает
    соединение, а молча считать такой ник свободным нельзя - именно так
    в выдачу попал npool, выставленный на аукцион.
    """
    html = None
    for attempt in (1, 2):
        try:
            html = _fetch(name)
            break
        except Exception:
            if attempt == 2:
                return ERROR
            time.sleep(0.7)

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
