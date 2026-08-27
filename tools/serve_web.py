"""
表示ページ(output/web)を http:// で配るだけの、開発確認用サーバー。

run.py は file:// でページを直接開く方式なので、普段はこれを使う必要はない。
使うのは次の2つの場合だけ。
  1. file:// ではブラウザの制限で動かない機能を確かめたい時
  2. スマートグラスやスマホなど、別の機械から同じ画面を見たい時

使い方: python tools/serve_web.py  → http://localhost:8080 を開く
"""
import functools
import http.server
import os
import socketserver

PORT = 8080
WEB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "web"
)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # 直したCSSやJSが古いまま表示されるのを防ぐ（開発中は毎回読み直させる）
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    handler = functools.partial(QuietHandler, directory=WEB_DIR)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        print(f"[配信中] http://localhost:{PORT}  ({WEB_DIR})")
        print("Ctrl+C で停止")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n停止しました。")


if __name__ == "__main__":
    main()
