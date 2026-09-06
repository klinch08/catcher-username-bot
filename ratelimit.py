# -*- coding: utf-8 -*-
"""Ограничитель частоты запросов - «дырявое ведро» с токенами.

Раньше стоял жёсткий интервал между запросами: каждый поток ждал, пока
пройдёт 1/N секунды с прошлого запроса. При одном пользователе это работало,
но при нескольких они выстраивались в общую очередь и поиск у каждого
растягивался.

Здесь вместо интервала копится запас токенов. Пока запас есть, потоки уходят
без ожидания, и несколько поисков идут параллельно. Средняя частота при этом
всё равно не превышает заданную.
"""

import threading
import time


class Limiter(object):
    def __init__(self, rate, burst=None):
        self.rate = float(rate)              # запросов в секунду в среднем
        self.burst = float(burst or rate)    # сколько можно выпустить разом
        self._tokens = self.burst
        self._updated = time.time()
        self._lock = threading.Lock()

    def acquire(self):
        """Дождаться своей очереди. Если запас есть - вернётся сразу."""
        while True:
            with self._lock:
                now = time.time()
                self._tokens = min(self.burst,
                                   self._tokens + (now - self._updated) * self.rate)
                self._updated = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                # токенов нет - считаем, через сколько появится следующий
                wait = (1 - self._tokens) / self.rate
            time.sleep(wait)
