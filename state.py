# -*- coding: utf-8 -*-
"""Настройки пользователей и списки магнита, хранятся в JSON."""

import io
import json
import os
import threading

import config

_lock = threading.Lock()
_data = {}

DEFAULTS = {
    "pattern": "mix",    # активный шаблон генерации
    "word": "",          # исходное слово для режима анаграмм
}


def load():
    global _data
    if os.path.exists(config.STATE_FILE):
        try:
            with io.open(config.STATE_FILE, encoding="utf-8") as f:
                _data = json.load(f)
        except Exception:
            _data = {}


def _save():
    tmp = config.STATE_FILE + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(_data, ensure_ascii=False, indent=2))
    os.replace(tmp, config.STATE_FILE)


def get(user_id):
    """Настройки пользователя, с подстановкой умолчаний."""
    import names   # локально, чтобы не было кольцевого импорта

    with _lock:
        user = _data.setdefault(str(user_id), {})
        for key, val in DEFAULTS.items():
            user.setdefault(key, list(val) if isinstance(val, list) else val)
        # фильтр мог быть удалён из бота - тогда откатываем на умолчание
        if user["pattern"] not in names.PATTERNS and user["pattern"] != "anagram":
            user["pattern"] = DEFAULTS["pattern"]
            _save()
        return dict(user)


def set_value(user_id, key, value):
    with _lock:
        _data.setdefault(str(user_id), {})[key] = value
        _save()


def reset(user_id):
    """Вернуть настройки пользователя к умолчаниям."""
    with _lock:
        _data[str(user_id)] = {}
        _save()
