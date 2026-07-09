"""
output/web/ をキャッシュ無効化ヘッダー付きで配信する開発用サーバー。
編集を即座にブラウザへ反映させるため（ブラウザキャッシュ対策）。
使い方: python tools/serve_web.py
"""
import http.server
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output", "web")


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer(("", config.WEB_PORT), NoCacheHandler)
    print(f"http://localhost:{config.WEB_PORT} を配信中（Ctrl+Cで停止）")
    server.serve_forever()
