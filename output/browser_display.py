"""WebSocket経由でブラウザに字幕・方向データを送信する出力実装。"""
import asyncio
import json
import websockets
from .base import DisplayBase, SubtitleEvent


class BrowserDisplay(DisplayBase):
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self._clients: set = set()
        self._server = None

    async def start(self) -> None:
        self._server = await websockets.serve(
            self._register_client, self.host, self.port
        )
        print(f"[BrowserDisplay] WebSocket起動: ws://{self.host}:{self.port}")

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _register_client(self, websocket, path=None):
        self._clients.add(websocket)
        print(f"[BrowserDisplay] クライアント接続 (計{len(self._clients)}台)")
        try:
            await websocket.wait_closed()
        finally:
            self._clients.discard(websocket)

    async def send(self, event: SubtitleEvent) -> None:
        if not self._clients:
            return
        payload = json.dumps({
            "type": "subtitle",
            "text": event.text,
            "direction": event.direction,
        }, ensure_ascii=False)
        await asyncio.gather(
            *[client.send(payload) for client in self._clients],
            return_exceptions=True,
        )
