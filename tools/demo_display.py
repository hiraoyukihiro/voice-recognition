"""
画面（字幕・方向の円弧・音イベント）だけを確かめるための偽データ送信ツール。

マイクもAIも使わず、run.py と同じ形のお知らせをWebSocketで流すだけ。
「画面の作りが正しいか」と「マイクやAIが正しいか」を分けて切り分けられる。

使い方:
  python tools/demo_display.py
  そのあと output/web/index.html をブラウザで開く（run.py は止めておくこと）
"""
import asyncio
import json
import os
import random
import sys

import websockets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

clients = set()

SUBTITLES = [
    "おはようございます",
    "今日の授業は3時間目からです",
    "そこの荷物、取ってもらえますか",
    "電車が遅れているみたいだよ",
]

SOUNDS = [
    ("doorbell", "インターホン", "🔔"),
    ("knock", "ノックの音", "🚪"),
    ("phone", "電話の着信", "📞"),
    ("fire_alarm", "火災報知器", "🔥"),
    ("dog", "犬の鳴き声", "🐕"),
    ("water", "水の音", "🚿"),
]


async def handler(websocket, path=None):
    clients.add(websocket)
    print(f"[ブラウザ接続] 現在{len(clients)}台")
    await websocket.send(json.dumps({
        "type": "config",
        "sectors": config.DIRECTION_SECTORS,
        "max_sources": config.MAX_SOUND_SOURCES,
        "sound_history": config.SOUND_EVENT_HISTORY,
        "subtitle_lines": config.SUBTITLE_LINES,
        "arc_lifetime": config.SOURCE_ARC_LIFETIME,
        "subtitle_view": config.SUBTITLE_VIEW,
    }, ensure_ascii=False))
    try:
        await websocket.wait_closed()
    finally:
        clients.discard(websocket)


async def send(payload):
    if not clients:
        return
    msg = json.dumps(payload, ensure_ascii=False)
    await asyncio.gather(*[c.send(msg) for c in clients], return_exceptions=True)


async def subtitle_demo():
    while True:
        text = random.choice(SUBTITLES)
        direction = random.choice([0, 45, 90, 150, 210, 270, 315])
        # 1文字ずつ増やして「認識途中」の見え方も確かめる
        for i in range(1, len(text) + 1):
            await send({"type": "subtitle", "text": text[:i],
                        "direction": direction, "is_final": False})
            await asyncio.sleep(0.12)
        await send({"type": "subtitle", "text": text,
                    "direction": direction, "is_final": True})
        await asyncio.sleep(2.0)


async def sound_demo():
    while True:
        await asyncio.sleep(3.5)
        key, name, icon = random.choice(SOUNDS)
        await send({"type": "sound_event", "key": key, "name": name, "icon": icon,
                    "confidence": round(random.uniform(0.55, 0.95), 2),
                    "db": 58.0, "direction": random.randint(0, 359)})


async def direction_demo():
    angle = 0.0
    while True:
        await asyncio.sleep(config.DIRECTION_BROADCAST_INTERVAL)
        angle = (angle + 7) % 360
        await send({"type": "direction", "direction": angle, "level": 0.05})


async def main():
    server = await websockets.serve(handler, config.WEBSOCKET_HOST, config.WEBSOCKET_PORT)
    print(f"[デモ送信中] ws://{config.WEBSOCKET_HOST}:{config.WEBSOCKET_PORT}")
    print("output/web/index.html をブラウザで開いてください（Ctrl+Cで停止）")
    await asyncio.gather(subtitle_demo(), sound_demo(), direction_demo())
    server.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n停止しました。")
