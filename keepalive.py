# -*- coding: utf-8 -*-
"""Пустой HTTP-сервер для бесплатных хостингов вроде Render.

Такие хостинги дают только веб-сервисы: они ждут, что программа слушает порт,
и усыпляют её без входящих запросов. Бот порт не слушает - он сам стучится
в Telegram, поэтому поднимаем заглушку, которую будет дёргать пингер.
"""

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("bot is alive".encode("utf-8"))

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass   # не засоряем лог пингами


def start():
    """Поднять заглушку в фоне. Порт хостинг передаёт в PORT."""
    port = int(os.environ.get("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return port
