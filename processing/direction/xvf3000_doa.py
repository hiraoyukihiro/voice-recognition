"""
reSpeaker Mic Array v2.0 (XVF3000) 実機DOA実装。
USB制御転送でデバイス内蔵のDOAから方向角度を直接取得する（audio引数は使わない）。

事前準備: Zadig で「SEEED Control (Interface 3)」(USB ID 2886 0018 03) に
WinUSB ドライバを入れておくこと。入っていないと "Entity not found" になる。

参考: https://github.com/respeaker/usb_4_mic_array  tuning.py
      DOAANGLE = (id=21, offset=0, int, 0〜359)
"""
import sys
import struct
import threading

import numpy as np
import usb.core
import usb.util

from .base import DirectionEstimatorBase

VENDOR_ID = 0x2886
PRODUCT_ID = 0x0018

# (パラメータID, オフセット) tuning.py の PARAMETERS より
DOAANGLE = (21, 0)
VOICEACTIVITY = (19, 32)

POLL_INTERVAL = 0.1


class XVF3000DOA(DirectionEstimatorBase):
    """
    XVF3000 の DOAANGLE（0〜359度）を読み、校正して返す。
    XVF3800DOA と同じく、別スレッドで0.1秒ごとに読んでキャッシュする。

    angle_offset / invert は設置向きの校正用。
    config.py の XVF3000_ANGLE_OFFSET / XVF3000_INVERT で調整する。
    """

    TIMEOUT = 1000

    def __init__(self, angle_offset: float = 0.0, invert: bool = False,
                 vendor_id: int = VENDOR_ID, product_id: int = PRODUCT_ID):
        self.angle_offset = angle_offset
        self.invert = invert
        self.dev = self._find_device(vendor_id, product_id)
        if self.dev is None:
            raise RuntimeError(
                "reSpeaker XVF3000が見つかりません。USB接続を確認してください "
                f"(VID=0x{vendor_id:04X}, PID=0x{product_id:04X})。"
            )
        # ドライバ未設定だとここで "Entity not found" になるので、起動時に分かるよう1回読んでおく
        try:
            self._read_int(*DOAANGLE)
        except usb.core.USBError as e:
            raise RuntimeError(
                f"XVF3000のUSB制御に失敗しました（{e}）。"
                "Zadigで SEEED Control (Interface 3) に WinUSB を入れてください。"
            ) from e
        self._last_angle = 0.0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)

    @staticmethod
    def _find_device(vid: int, pid: int):
        if sys.platform.startswith("win"):
            import libusb_package
            return libusb_package.find(idVendor=vid, idProduct=pid)
        return usb.core.find(idVendor=vid, idProduct=pid)

    def _read_int(self, param_id: int, offset: int) -> int:
        # tuning.py の read(): int型は cmd に 0x40 を立て、8バイト返ってくる先頭4バイトが値
        cmd = 0x80 | 0x40 | offset
        response = self.dev.ctrl_transfer(
            usb.util.CTRL_IN | usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_RECIPIENT_DEVICE,
            0, cmd, param_id, 8, self.TIMEOUT,
        )
        return struct.unpack("<ii", response.tobytes())[0]

    def is_voice(self) -> bool:
        """XVF3000内蔵の音声検出（VAD）。声がしていればTrue。"""
        return self._read_int(*VOICEACTIVITY) == 1

    def _read_and_cache(self) -> None:
        deg = float(self._read_int(*DOAANGLE))
        if self.invert:
            deg = -deg
        deg = (deg + self.angle_offset) % 360
        with self._lock:
            self._last_angle = deg

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._read_and_cache()
            except Exception:
                pass
            self._stop_event.wait(POLL_INTERVAL)

    def _read_and_cache_safe(self) -> None:
        try:
            self._read_and_cache()
        except Exception:
            pass

    def start(self) -> None:
        if not self._poll_thread.is_alive():
            self._read_and_cache_safe()
            self._poll_thread.start()

    def estimate(self, audio: np.ndarray) -> float:
        if self._poll_thread.is_alive():
            with self._lock:
                return self._last_angle
        self._read_and_cache_safe()
        return self._last_angle

    def close(self):
        self._stop_event.set()
        if self._poll_thread.is_alive():
            self._poll_thread.join(timeout=POLL_INTERVAL * 3)
        usb.util.dispose_resources(self.dev)
