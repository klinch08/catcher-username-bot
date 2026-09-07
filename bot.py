# -*- coding: utf-8 -*-
"""Телеграм-бот: подбор свободных ников. Экраны с картинками."""

import io
import json
import os
import threading
import time
import urllib.parse
import urllib.request

import checker
import config
import keepalive
import names

API = "https://api.telegram.org/bot" + config.BOT_TOKEN + "/"

PATTERN_TITLES = {
    "mix": "Читаемые, но не слова",
    "anagram": "Из своего слова",
    "junk": "Мусорные, без гласных",
    "digit": "Буквы и цифра",
    "rand": "Случайные",
}

# Картинка-шапка для каждого экрана.
SCREEN_IMAGES = {
    "menu": "menu_us.png",
    "search": "poisk_us.png",
    "searching": "poiskcycl_us.png",
    "filters": "filters_us.png",
    "anagram": "anagramma_us.png",
    "results": "results_us.png",
}

# Чего бот ждёт от пользователя следующим сообщением.
pending = {}

_log_lock = threading.Lock()
_photo_ids = {}

# Единственное сообщение бота в каждом чате: chat_id -> message_id.
# Всё происходит внутри него, новые сообщения не плодим.
_last_msg = {}


def log(*parts):
    """Пишем и в консоль, и в bot.log."""
    line = time.strftime("%H:%M:%S ") + " ".join(str(p) for p in parts)
    print(line)
    try:
        with _log_lock, io.open("bot.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# --------------------------------------------------------------------------- api

def api(method, **params):
    for key, val in list(params.items()):
        if isinstance(val, (dict, list)):
            params[key] = json.dumps(val, ensure_ascii=False)
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(API + method, data=data)
    with urllib.request.urlopen(req, timeout=70) as r:
        return json.loads(r.read().decode())


def api_upload(method, field, path, **params):
    """Загрузка файла через multipart - нужна для первой отправки картинки."""
    boundary = "----botboundary%d" % int(time.time() * 1000)
    body = b""
    for key, val in params.items():
        if isinstance(val, (dict, list)):
            val = json.dumps(val, ensure_ascii=False)
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                 % (boundary, key, val)).encode("utf-8")
    with io.open(path, "rb") as f:
        blob = f.read()
    body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
             "Content-Type: image/png\r\n\r\n"
             % (boundary, field, os.path.basename(path))).encode("utf-8")
    body += blob + ("\r\n--%s--\r\n" % boundary).encode("utf-8")

    req = urllib.request.Request(
        API + method, data=body,
        headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())


def load_photo_cache():
    global _photo_ids
    if os.path.exists(config.IMAGE_CACHE):
        try:
            with io.open(config.IMAGE_CACHE, encoding="utf-8") as f:
                _photo_ids = json.load(f)
        except Exception:
            _photo_ids = {}


def save_photo_cache():
    try:
        with io.open(config.IMAGE_CACHE, "w", encoding="utf-8") as f:
            f.write(json.dumps(_photo_ids, ensure_ascii=False))
    except Exception:
        pass


def photo_path(screen):
    return os.path.join(config.IMAGE_DIR, SCREEN_IMAGES.get(screen, ""))


def send_text(chat_id, text, keyboard=None):
    params = {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    if keyboard:
        params["reply_markup"] = {"inline_keyboard": keyboard}
    try:
        return api("sendMessage", **params)
    except Exception as e:
        log("send failed:", e)


def answer(query_id, text=None, alert=False):
    """Ответить на нажатие кнопки. С текстом - всплывашкой поверх чата."""
    params = {"callback_query_id": query_id}
    if text:
        params["text"] = text
        params["show_alert"] = "true" if alert else "false"
    try:
        api("answerCallbackQuery", **params)
    except Exception:
        pass


def remember(chat_id, resp):
    """Запомнить id только что отправленного сообщения."""
    msg_id = ((resp or {}).get("result") or {}).get("message_id")
    if msg_id:
        _last_msg[chat_id] = msg_id
    return msg_id


def drop_message(chat_id, message_id):
    """Убрать сообщение из чата. В личке боту разрешено удалять и чужие."""
    try:
        api("deleteMessage", chat_id=chat_id, message_id=message_id)
    except Exception:
        pass   # старше 48 часов или уже удалено - не беда


def show(chat_id, screen, text, keyboard=None, message_id=None):
    """Показать экран: картинка-шапка плюс текст под ней.

    Первый раз картинка заливается файлом, дальше используется file_id.
    Если сообщение уже есть - меняем в нём и картинку, и подпись.
    """
    # если экран вызван без привязки - правим то сообщение, что уже висит
    if message_id is None:
        message_id = _last_msg.get(chat_id)

    path = photo_path(screen)
    markup = {"inline_keyboard": keyboard} if keyboard else None
    # у подписи к фото лимит 1024 символа
    caption = text if len(text) <= 1024 else text[:1000] + "\n..."

    file_id = _photo_ids.get(screen)

    if message_id:
        # правим существующее сообщение, чтобы никогда не плодить новые
        try:
            if file_id:
                params = {"chat_id": chat_id, "message_id": message_id,
                          "media": {"type": "photo", "media": file_id,
                                    "caption": caption}}
                if markup:
                    params["reply_markup"] = markup
                api("editMessageMedia", **params)
            elif os.path.exists(path):
                # картинки ещё нет на серверах Telegram - заливаем прямо
                # в это же сообщение через attach://
                params = {"chat_id": chat_id, "message_id": message_id,
                          "media": {"type": "photo", "media": "attach://photo",
                                    "caption": caption}}
                if markup:
                    params["reply_markup"] = markup
                resp = api_upload("editMessageMedia", "photo", path, **params)
                sizes = (resp.get("result") or {}).get("photo") or []
                if sizes:
                    _photo_ids[screen] = sizes[-1]["file_id"]
                    save_photo_cache()
            else:
                edit_caption(chat_id, message_id, text, keyboard)
            _last_msg[chat_id] = message_id
            return message_id
        except Exception as e:
            # содержимое совпало с текущим - Telegram отвечает ошибкой,
            # но сообщение на месте, и новое слать не надо
            if "not modified" in str(e):
                _last_msg[chat_id] = message_id
                return message_id
            log("editMessageMedia:", e)   # не вышло - шлём новое

    try:
        if file_id:
            resp = api("sendPhoto", chat_id=chat_id, photo=file_id,
                       caption=caption, reply_markup=markup or {})
        elif os.path.exists(path):
            resp = api_upload("sendPhoto", "photo", path, chat_id=chat_id,
                              caption=caption, reply_markup=markup or {})
            sizes = resp["result"].get("photo") or []
            if sizes:
                _photo_ids[screen] = sizes[-1]["file_id"]
                save_photo_cache()
        else:
            return remember(chat_id, send_text(chat_id, text, keyboard))
        new_id = resp["result"]["message_id"]
        _last_msg[chat_id] = new_id
        return new_id
    except Exception as e:
        log("show failed:", e)
        return remember(chat_id, send_text(chat_id, text, keyboard))


def edit_caption(chat_id, message_id, text, keyboard=None):
    """Поменять только подпись под картинкой - для прогресса поиска."""
    params = {"chat_id": chat_id, "message_id": message_id,
              "caption": text if len(text) <= 1024 else text[:1000] + "\n..."}
    if keyboard:
        params["reply_markup"] = {"inline_keyboard": keyboard}
    try:
        api("editMessageCaption", **params)
    except Exception:
        pass


# ----------------------------------------------------------------------- клавиатуры

# Пробелы растягивают кнопки - иначе окно меню выглядит узким.
PAD = " " * 6

# Эмодзи на кнопках. У выбранного фильтра значок меняется на галочку.
ICON_SEARCH = "🔍"     # лупа
ICON_GEAR = "⚙️"     # шестерёнка
ICON_CHECK = "✅"          # зелёная галочка
ICON_REFRESH = "🔄"    # круговая стрелка
ICON_DICE = "🎲"       # кубик
ICON_BACK = "⬅️"       # стрелка влево

# Свои значки у фильтров - подменяются галочкой, когда фильтр выбран.
PATTERN_ICONS = {
    "rand": ICON_DICE,
}

DEFAULT_PATTERN = "mix"


def btn(text, data, style=None):
    """style: success - зелёная, primary - синяя, danger - красная (Bot API 9.4)."""
    button = {"text": text, "callback_data": data}
    if style:
        button["style"] = style
    return button


def pack(action, arg, pattern, word):
    """Настройки едут прямо в кнопке.

    Так бот не зависит от диска: Render стирает файлы при каждом
    перезапуске, а кнопки живут в сообщении и переживают что угодно.
    Лимит callback_data - 64 байта, наши поля в него укладываются.
    """
    return ":".join((action, str(arg), pattern, word))


def unpack(data):
    """Разобрать callback_data обратно."""
    parts = (data.split(":") + ["", "", ""])[:4]
    action, arg, pattern, word = parts
    if pattern not in PATTERN_TITLES:
        pattern = DEFAULT_PATTERN
    return action, arg, pattern, word


def kb_menu(pattern, word):
    return [
        [btn(PAD + ICON_SEARCH + " Поиск" + PAD,
             pack("go", "search", pattern, word), "success")],
        [btn(PAD + ICON_GEAR + " Фильтры" + PAD,
             pack("go", "filters", pattern, word))],
    ]


def kb_search(pattern, word):
    return [
        [btn("5 символов", pack("run", 5, pattern, word)),
         btn("6 символов", pack("run", 6, pattern, word))],
        [btn(PAD + ICON_GEAR + " Фильтры" + PAD,
             pack("go", "filters", pattern, word))],
        [btn(PAD + ICON_BACK + " В меню" + PAD,
             pack("go", "main", pattern, word))],
    ]


def kb_filters(pattern, word):
    rows = []
    for key, title in PATTERN_TITLES.items():
        if key == "anagram" and word:
            title += " (%s)" % word
        icon = ICON_CHECK if pattern == key else PATTERN_ICONS.get(key)
        rows.append([btn(("%s %s" % (icon, title)) if icon else title,
                         pack("set", key, pattern, word))])
    rows.append([btn(ICON_REFRESH + " Сбросить настройки",
                     pack("reset", "", pattern, word))])
    rows.append([btn(PAD + ICON_BACK + " В меню" + PAD,
                     pack("go", "main", pattern, word))])
    return rows


def kb_back(pattern, word):
    """Возврат с экрана анаграмм - обратно в фильтры, откуда сюда и пришли."""
    return [[btn(PAD + ICON_BACK + " Вернуться к фильтрам" + PAD,
                 pack("go", "filters", pattern, word))]]


def kb_results(length, pattern, word):
    return [
        [btn(PAD + ICON_REFRESH + " Ещё раз" + PAD,
             pack("run", length, pattern, word), "primary")],
        [btn(PAD + ICON_BACK + " В меню" + PAD,
             pack("go", "main", pattern, word))],
    ]


# --------------------------------------------------------------------------- тексты

TEXT_MENU = "Подбор свободных ников\n\nВыбери раздел ниже:"

TEXT_SEARCH = ("Выбери длину ника.\n\n"
               "Поиск идёт %d секунд и останавливается раньше, как только "
               "наберётся %d свободных." % (config.DURATION, config.MAX_FOUND))

TEXT_FILTERS = "Какими будут ники:"

TEXT_ANAGRAM = ("Пришли слово - соберу из его букв перестановки "
                "и проверю, какие свободны.\n\n"
                "ivanov -> navovi, onaviv, ovavin")


# ------------------------------------------------------------------------ действия

DOT_FRAMES = ("...", "..", ".", "..")


def animate_dots(chat_id, message_id, stop, base="Идёт поиск юзернеймов"):
    """Циклично гоняем точки в подписи, пока поиск не закончится.

    Проверяем флаг и перед правкой тоже: поиск может закончиться, пока мы
    спим, и тогда лишняя правка затрёт готовый результат вместе с кнопками.
    """
    i = 0
    while not stop.is_set():
        edit_caption(chat_id, message_id, base + DOT_FRAMES[i % len(DOT_FRAMES)])
        i += 1
        stop.wait(0.6)
        if stop.is_set():
            return


def run_bg(fn, *args):
    """Долгие задачи - в отдельном потоке, чтобы бот отвечал во время поиска."""
    def guarded():
        try:
            fn(*args)
        except Exception as e:
            log("фоновая задача упала:", repr(e))

    threading.Thread(target=guarded, daemon=True).start()


def format_results(free, checked, spent, errors):
    if free:
        text = "Свободны: %d (проверено %d за %d сек)\n\n" % (
            len(free), checked, spent)
        text += "\n".join("@" + n for n in free)
        text += "\n\nЗанимай в настройках профиля, пока не увели."
    else:
        text = ("Свободных нет, проверено %d за %d сек.\n"
                "Попробуй другой фильтр или длину побольше." % (checked, spent))
    if errors:
        text += "\n\nНе удалось проверить: %d - сеть." % errors
    return text


def do_search(chat_id, length, pattern, word, message_id=None):
    """Крутить пачки, пока не выйдет время или не наберётся MAX_FOUND ников."""
    anagram_of = word if pattern == "anagram" else None

    if pattern == "anagram" and not anagram_of:
        show(chat_id, "filters", "Сначала пришли слово: Фильтры, «Из своего слова».",
             kb_filters(pattern, word), message_id)
        return

    if anagram_of:
        length = len(anagram_of)
    head = "Идёт поиск юзернеймов..."

    # во время поиска - своя картинка и бегущие точки, результат покажем потом
    message_id = show(chat_id, "searching", head, None, message_id)
    stop = threading.Event()
    ticker = threading.Thread(target=animate_dots,
                              args=(chat_id, message_id, stop), daemon=True)
    ticker.start()

    started = time.time()
    seen, free = set(), []
    checked = errors = 0

    try:
        while (time.time() - started < config.DURATION
               and len(free) < config.MAX_FOUND):
            pool = (names.anagrams(anagram_of, config.BATCH) if anagram_of
                    else names.generate(length, pattern, config.BATCH))
            batch = [n for n in pool if n not in seen]
            if not batch:
                # генератор выдохся: либо варианты кончились, либо фильтр
                # производит только то, что мы сами же и отсеиваем
                if not checked:
                    show(chat_id, "results",
                         "Этот фильтр не даёт подходящих ников.\n"
                         "Выбери другой в настройках.",
                         kb_results(length, pattern, word), message_id)
                    return
                break
            seen.update(batch)

            for name, status, _kind in checker.check_many(batch):
                checked += 1
                if status == checker.FREE:
                    free.append(name)
                elif status == checker.ERROR:
                    errors += 1
    finally:
        # гасим анимацию при любом исходе: если поиск упадёт, а флаг
        # не выставить, точки будут крутиться вечно
        stop.set()
        ticker.join(timeout=3)

    free.sort(key=names.readability, reverse=True)
    text = format_results(free[:config.MAX_FOUND], checked,
                          time.time() - started, errors)
    show(chat_id, "results", text, kb_results(length, pattern, word),
         message_id)


def set_anagram_word(chat_id, user_id, raw, message_id=None):
    """Принять слово для режима анаграмм, отсеяв заведомо бесполезные."""
    word = raw.strip().lstrip("@").lower()

    problem = None
    if not names.is_valid(word):
        problem = ("«%s» не годится: нужно 5-32 символа, только a-z, 0-9 "
                   "и подчёркивание, первый символ - буква." % word)
    elif not names.enough_variety(word):
        problem = ("В «%s» слишком мало разных букв - перестановки выйдут "
                   "почти одинаковые, и Telegram такие не отдаёт. "
                   "Нужно минимум 4 разные буквы." % word)
    elif len(names.anagrams(word, 5)) < 3:
        problem = "Из «%s» толком не переставить буквы." % word

    if problem:
        pending[user_id] = "anagram_word"
        show(chat_id, "anagram", problem + "\n\nПришли другое слово.",
             kb_back("anagram", ""))
        return

    example = ", ".join(names.anagrams(word, 3))
    show(chat_id, "filters",
         "Готово, слово «%s». Например: %s\n\n"
         "Теперь жми Поиск - переберу перестановки и покажу свободные."
         % (word, example), kb_filters("anagram", word))


# --------------------------------------------------------------------- обработчики

def allowed(user_id):
    return not config.ALLOWED_USERS or user_id in config.ALLOWED_USERS


def handle_message(msg):
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    text = msg.get("text", "").strip()
    if not allowed(user_id):
        return

    # убираем написанное пользователем: в чате должно висеть
    # ровно одно сообщение - наше
    drop_message(chat_id, msg["message_id"])

    want = pending.pop(user_id, None)
    if want == "anagram_word" and not text.startswith("/"):
        set_anagram_word(chat_id, user_id, text)
        return

    show(chat_id, "menu", TEXT_MENU, kb_menu(DEFAULT_PATTERN, ""))


def handle_callback(query):
    chat_id = query["message"]["chat"]["id"]
    message_id = query["message"]["message_id"]
    user_id = query["from"]["id"]
    if not allowed(user_id):
        return

    action, arg, pattern, word = unpack(query.get("data", ""))

    # нажали на уже выбранный фильтр - незачем перерисовывать экран
    if action == "set" and arg == pattern and arg != "anagram":
        answer(query["id"], "Фильтр «%s» уже выбран" % PATTERN_TITLES[arg], True)
        return

    if action == "reset" and pattern == DEFAULT_PATTERN and not word:
        answer(query["id"], "Настройки и так стоят по умолчанию", True)
        return

    answer(query["id"])

    if action == "go":
        if arg == "main":
            show(chat_id, "menu", TEXT_MENU, kb_menu(pattern, word), message_id)
        elif arg == "search":
            show(chat_id, "search", TEXT_SEARCH, kb_search(pattern, word), message_id)
        elif arg == "filters":
            show(chat_id, "filters", TEXT_FILTERS, kb_filters(pattern, word),
                 message_id)

    elif action == "run":
        run_bg(do_search, chat_id, int(arg), pattern, word, message_id)

    elif action == "reset":
        show(chat_id, "filters", "Настройки сброшены.\n\n" + TEXT_FILTERS,
             kb_filters(DEFAULT_PATTERN, ""), message_id)

    elif action == "set":
        if arg == "anagram":
            pending[user_id] = "anagram_word"
            show(chat_id, "anagram", TEXT_ANAGRAM, kb_back(arg, word), message_id)
        else:
            show(chat_id, "filters", TEXT_FILTERS, kb_filters(arg, word), message_id)


# --------------------------------------------------------------------------- запуск

def main():
    if not config.BOT_TOKEN:
        log("Нет токена: положи его в token.txt или в переменную BOT_TOKEN")
        return
    load_photo_cache()
    # на хостингах-веб-сервисах нужна заглушка, которую будет дёргать пингер
    if os.environ.get("PORT"):
        log("Заглушка для пингера на порту %d" % keepalive.start())
    me = api("getMe")["result"]
    log("Запущен как @%s" % me["username"])

    offset = 0
    while True:
        try:
            resp = api("getUpdates", offset=offset, timeout=60)
        except Exception as e:
            log("polling error:", e)
            time.sleep(3)
            continue
        for upd in resp.get("result", []):
            offset = upd["update_id"] + 1
            try:
                if "message" in upd:
                    handle_message(upd["message"])
                elif "callback_query" in upd:
                    handle_callback(upd["callback_query"])
            except Exception as e:
                log("handler error:", e)


if __name__ == "__main__":
    main()
