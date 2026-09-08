# -*- coding: utf-8 -*-
"""Генерация кандидатов в ники."""

import random
import string

LETTERS = string.ascii_lowercase
DIGITS = string.digits
VOWELS = "aeiou"
CONSONANTS = "bcdfgjklmnprstvwz"

# Правила Telegram: 5-32 символа, но пятибуквенные Telegram держит
# у себя и на попытку занять отвечает "username is invalid",
# поэтому рабочий минимум - 6.
# Формально:, a-z 0-9 _, первый символ - буква,
# последний - не подчёркивание, двух подчёркиваний подряд быть не может.
MIN_LEN = 5


def _pronounceable(length):
    """Чередование согласная/гласная - такие читаются как слово."""
    out = []
    for i in range(length):
        out.append(random.choice(CONSONANTS if i % 2 == 0 else VOWELS))
    return "".join(out)


def _letters_digit(length):
    """Буквы плюс цифра в конце."""
    return "".join(random.choice(LETTERS) for _ in range(length - 1)) + random.choice(DIGITS)


def _random(length):
    return "".join(random.choice(LETTERS) for _ in range(length))


PATTERNS = {
    "digit": _letters_digit,
    "rand": _random,
}


def generate(length=5, pattern="pron", count=20):
    """Вернуть count уникальных кандидатов заданной длины."""
    fn = PATTERNS.get(pattern, _pronounceable)
    seen = set()
    # ограничение по попыткам, чтобы не крутиться вечно на коротких длинах
    for _ in range(count * 200):
        if len(seen) >= count:
            break
        name = fn(length)
        # для mirror/rep разнообразие недостижимо по построению - там не режем
        if (is_valid(name) and enough_variety(name)
                and not looks_like_word(name) and not is_mirror(name)):
            seen.add(name)
    return sorted(seen)


def is_valid(name):
    """Проверка ника по формальным правилам Telegram."""
    if not (MIN_LEN <= len(name) <= 32):
        return False
    if name[0] not in LETTERS:
        return False
    if name[-1] == "_":
        return False
    if "__" in name:
        return False
    return all(c in LETTERS + DIGITS + "_" for c in name)


def _readability(name):
    """Чем меньше, тем легче читается: штрафуем скопления согласных."""
    worst = run = 0
    for ch in name:
        run = run + 1 if ch in CONSONANTS or ch not in VOWELS + DIGITS else 0
        worst = max(worst, run)
    return worst


def anagrams(word, count=20):
    """Перестановки букв слова: durov -> vodur, rudov и т.д.

    Возвращает самые читаемые варианты, исходное слово исключено.
    """
    word = word.lower().lstrip("@")
    letters = list(word)
    seen = set()
    for _ in range(count * 300):
        if len(seen) >= count * 4:
            break
        random.shuffle(letters)
        variant = "".join(letters)
        if variant != word and is_valid(variant):
            seen.add(variant)
    # сначала те, что читаются как слово
    return sorted(seen, key=lambda n: (_readability(n), n))[:count]


# Совсем вырожденные ники Telegram придерживает, но порог тут низкий:
# gagmg с тремя разными буквами занялся, swwww с двумя - тоже. Симметричные
# отсекаются отдельно, через is_mirror.
MIN_DISTINCT = 2


def enough_variety(name):
    """Хватает ли в нике разных символов, чтобы Telegram его отдал."""
    return len(set(name)) >= min(MIN_DISTINCT, len(name))


def _junk(length):
    """Некрасивый ник: скопления согласных, мало гласных.

    Красивые произносимые имена Telegram придерживает под аукцион и на
    попытку занять отвечает "username is invalid". А вот такие, как kljyy
    или lruov, отдаются свободно - они никому не нужны как товар.
    """
    hard = "bcdfgjklmnpqrstvwxz"
    out = [random.choice(hard) for _ in range(length)]
    # одна гласная максимум, и не в середине - чтобы не получилось слово
    if random.random() < 0.5:
        pos = random.choice([0, length - 1, length - 2])
        out[pos] = random.choice(VOWELS)
    return "".join(out)


def ugliness(name):
    """Насколько ник далёк от произносимого: чем больше, тем лучше шанс занять."""
    vowels = sum(1 for ch in name if ch in VOWELS)
    worst = run = 0
    for ch in name:
        run = 0 if ch in VOWELS else run + 1
        worst = max(worst, run)
    return worst * 2 - vowels




def readability(name):
    """Оценка читаемости 0-10: насколько ник похож на произносимое слово.

    Это ТОЛЬКО про удобство и красоту. Отдаст ли Telegram ник бесплатно,
    она не предсказывает: lruov и monaz читаются одинаково, но первый
    занялся, а второй ответил "username is invalid".
    """
    score = 10
    vowels = sum(1 for ch in name if ch in VOWELS)

    if vowels == 0:
        score -= 6
    elif vowels == 1:
        score -= 2

    # каждая лишняя согласная в скоплении бьёт по читаемости
    run = 0
    for ch in name:
        if ch in VOWELS:
            run = 0
        else:
            run += 1
            if run >= 2:
                score -= 1

    # одинаковые буквы подряд
    for i in range(len(name) - 1):
        if name[i] == name[i + 1]:
            score -= 1

    return max(0, min(10, score))


def _readable_junk(length):
    """Не слово, но и не абракадабра: гласные есть, произносимость сломана.

    Именно такие Telegram отдаёт: они не уходят на аукцион как красивые,
    но и читать их можно.
    """
    hard = "bcdfgjklmnprstvwz"
    out = []
    # ставим 2 гласные так, чтобы рядом обязательно был стык согласных
    slots = sorted(random.sample(range(length), 2))
    for i in range(length):
        out.append(random.choice(VOWELS) if i in slots else random.choice(hard))
    return "".join(out)


# Регистрируем шаблоны, объявленные после словаря.
PATTERNS["junk"] = _junk
PATTERNS["mix"] = _readable_junk


def looks_like_word(name):
    """Строгое чередование согласная-гласная - такие Telegram не отдаёт.

    Проверено на практике: jemag, monaz, wolak, sacir отвечают
    "username is invalid". А сработавшие kljyy, lruov, ougvg, avujl, nguad
    все имеют стык двух согласных или двух гласных подряд.
    """
    for i in range(len(name) - 1):
        if (name[i] in VOWELS) == (name[i + 1] in VOWELS):
            return False   # нашёлся стык - значит не словоподобный
    return True


def is_mirror(name):
    """Ник читается одинаково с обеих сторон - такие Telegram придерживает.

    Проверено: ovyvo, xmtmx, ltttl зеркальные и не отдаются, а gagmg
    с теми же тремя разными буквами, но без зеркальности, занялся.
    """
    return name == name[::-1]


def _repeats(length):
    """Одна буква повторяется трижды, места любые: swwww, oszzz, ababa."""
    letters = string.ascii_lowercase
    hero = random.choice(letters)
    # сколько раз повторить: три чаще всего, но бывает и больше
    times = random.choice((3, 3, 3, 4, min(5, length)))
    spots = random.sample(range(length), min(times, length))

    rest = [c for c in letters if c != hero]
    out = [hero if i in spots else random.choice(rest) for i in range(length)]
    return "".join(out)


PATTERNS["repeat"] = _repeats
