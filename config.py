# -*- coding: utf-8 -*-
"""Настройки бота."""

import os

# Токен от @BotFather
def _read_token():
    """Токен берём из переменной окружения, локально - из файла token.txt.

    В коде его держать нельзя: config.py уезжает в репозиторий, а по
    утёкшему токену бота уводят за пару часов.
    """
    from_env = os.environ.get("BOT_TOKEN", "").strip()
    if from_env:
        return from_env
    try:
        with open("token.txt", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


BOT_TOKEN = _read_token()

# Кому разрешено пользоваться ботом. Пустой список = всем.
# Свой id можно узнать у @userinfobot
ALLOWED_USERS = []

# Сколько запросов в секунду разрешено суммарно (t.me + Fragment).
RATE_LIMIT = 8

# Сколько ников проверять одновременно.
WORKERS = 8

# Размер одной пачки внутри поиска.
BATCH = 24

# Поиск идёт фиксированные 30 секунд, но останавливается раньше,
# как только наберётся MAX_FOUND свободных ников.
DURATION = 30
MAX_FOUND = 10

# Папка с картинками-шапками для экранов бота.
IMAGE_DIR = "images"

# Сюда кэшируются file_id загруженных картинок, чтобы не слать их заново.
IMAGE_CACHE = "images.json"

# Как часто "Магнит" перепроверяет отслеживаемые ники, секунд.
MAGNET_INTERVAL = 600


