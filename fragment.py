# -*- coding: utf-8 -*-
"""Проверка ника на аукционе Fragment.

Без неё бот отдаёт ники вроде ajict, которые на t.me выглядят свободными,
а в настройках Telegram отвечает "this link is taken, but it's available
for purchase" - потому что ник выставлен на аукцион.
"""

import re
import urllib.request

import config
import ratelimit

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

LISTED = "listed"      # выставлен или продан - бесплатно не занять
ABSENT = "absent"      # на Fragment нет, значит можно брать
ERROR = "error"

_limiter = ratelimit.Limiter(config.FRAGMENT_RATE)


def status(name):
    """LISTED / ABSENT / ERROR."""
    _limiter.acquire()
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
