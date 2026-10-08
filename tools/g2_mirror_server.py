"""
G2 画面ミラーの係（G2DoaServer.exe と一緒に使う、軽い中継サーバ）。

スマホの「G2 字幕+方向」(v0.4.9〜) は、G2 に出している画面の中身を
「音の方向」の PC の 8767 番にも送る。この係がそれを受け取り、PC のブラウザに配る。
方向（8765 番）は G2DoaServer.exe / start_app.bat のどちらが担当してもよい。マイクには触らない。

  python tools/g2_mirror_server.py          # 起動してブラウザを開く
  python tools/g2_mirror_server.py --no-open

exe にするとき（Windows の門番に別名で許可をもらうため。python.exe はパブリック網で止められている）:
  pyinstaller --onefile --name G2MirrorServer --add-data "output/web/g2_mirror.html;." tools/g2_mirror_server.py
"""
import argparse
import asyncio
import json
import os
import socket
import sys
import time
import webbrowser
from http import HTTPStatus

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

PORT = 8767


def page_path() -> str:
    # exe の中に同梱した時と、ソースのまま動かした時の両方に対応する
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "g2_mirror.html")
    return os.path.join(os.path.dirname(__file__), "..", "output", "web", "g2_mirror.html")


def lan_ips() -> list[str]:
    """この PC の同じ Wi-Fi 内での住所（スマホに入れる URL を案内するため）。"""
    ips = []
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # 実際には通信しない。どの出口を使うかを調べるだけ
        ips.append(s.getsockname()[0])
    except OSError:
        pass
    finally:
        s.close()
    return ips or ["(IP が取れません。ipconfig で確認)"]


clients: set = set()
last_mirror: dict | None = None


async def broadcast(data: dict, skip=None):
    msg = json.dumps(data, ensure_ascii=False)
    for c in list(clients):
        if c is skip:
            continue
        try:
            await c.send(msg)
        except ConnectionClosed:
            pass


async def handler(ws):
    global last_mirror
    clients.add(ws)
    print(f"[mirror] 接続 +1 （{len(clients)}）")
    try:
        if last_mirror is not None:
            await ws.send(json.dumps(last_mirror, ensure_ascii=False))
        async for message in ws:
            if isinstance(message, (bytes, bytearray)):
                continue
            try:
                data = json.loads(message)
            except ValueError:
                continue
            if isinstance(data, dict) and data.get("type") == "g2_mirror":
                data["received_at"] = time.time()
                last_mirror = data
                await broadcast(data, skip=ws)
    except ConnectionClosed:
        pass
    finally:
        clients.discard(ws)
        print(f"[mirror] 接続 -1 （{len(clients)}）")


def process_request(connection, request):
    """WebSocket ではなく普通にブラウザで開かれたら、ミラーの画面（HTML）を返す。"""
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return None
    with open(page_path(), "rb") as f:
        body = f.read()
    response = connection.respond(HTTPStatus.OK, "")
    response.body = body
    del response.headers["Content-Type"]
    del response.headers["Content-Length"]
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.headers["Content-Length"] = str(len(body))
    return response


async def main(args):
    async with serve(handler, "0.0.0.0", args.port, process_request=process_request):
        print(f"[mirror] listening on ws://0.0.0.0:{args.port}")
        print()
        print("=== G2 画面ミラー ===")
        print("  スマホの「G2 字幕+方向」の「音の方向」に、いつもの PC の URL を入れて接続すると、")
        print(f"  自動でこの PC の {args.port} 番にも画面が届きます。")
        for ip in lan_ips():
            print(f"  （この PC の住所: {ip}）")
        print(f"  PC で見る画面: http://localhost:{args.port}/")
        print("  方向は G2DoaServer.exe（または start_app.bat）を別に起動してください。")
        print("=====================")
        if not args.no_open:
            webbrowser.open(f"http://localhost:{args.port}/")
        await asyncio.Future()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="G2 画面ミラーの中継サーバ")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--no-open", action="store_true", help="ブラウザを自動で開かない")
    try:
        asyncio.run(main(ap.parse_args()))
    except KeyboardInterrupt:
        pass
    except OSError as e:
        print(f"エラー: {e}")
        print(f"（{PORT} 番がほかで使われていないか確認してください）")
        input("Enter キーで閉じます...")
