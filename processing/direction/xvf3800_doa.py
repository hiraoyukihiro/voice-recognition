"""
reSpeaker XVF3800 (XMOS) 実機DOA実装。
USB制御転送でデバイスから方向角度を直接取得する（audio引数は使わない）。

参考: https://github.com/respeaker/reSpeaker_XVF3800_USB_4MIC_ARRAY
      python_control/respeaker_get_doa.py
"""
import sys
import struct
import threading
import time

import numpy as np
import usb.core
import usb.util

from .base import DirectionEstimatorBase

VENDOR_ID = 0x2886
PRODUCT_ID = 0x001A

# resid, cmdid, length(bytes), type
AEC_AZIMUTH_VALUES = (33, 75, 16, "radians")

# 秒: バックグラウンドでUSBから方向を読み直す間隔。
# 方向はそんなに速く変わらないため、音声処理（0.3秒間隔）ごとに毎回USBへ
# 同期的に問い合わせるのではなく、別スレッドでこの間隔でだけ読んでキャッシュし、
# estimate()はキャッシュを返すだけにする（USB制御転送のレイテンシを認識パイプラインの
# クリティカルパスから外すため）。
POLL_INTERVAL = 0.1


class XVF3800DOA(DirectionEstimatorBase):
    """
    AEC_AZIMUTH_VALUES から4本のビーム角度（ラジアン）を読み、
    末尾の「自動選択ビーム」（DOA表示用）を度数に変換して返す。

    angle_offset / invert は設置向きに合わせた校正用パラメータ。
    実機接続後、既知の方向から発話して0度基準とズレがあれば
    config.py の XVF3800_ANGLE_OFFSET / XVF3800_INVERT を調整する。
    """

    # USB制御転送は本来数ms〜数十msで返るはずのため、詰まった場合に
    # イベントループ全体を長時間ブロックしないよう短いタイムアウトにする
    # （以前100秒に設定されており、詰まると認識・字幕表示全体が長時間停止していた）。
    TIMEOUT = 1000

    def __init__(self, angle_offset: float = 0.0, invert: bool = False,
                 vendor_id: int = VENDOR_ID, product_id: int = PRODUCT_ID):
        self.angle_offset = angle_offset
        self.invert = invert
        self.dev = self._find_device(vendor_id, product_id)
        if self.dev is None:
            raise RuntimeError(
                "reSpeaker XVF3800が見つかりません。USB接続を確認してください "
                f"(VID=0x{vendor_id:04X}, PID=0x{product_id:04X})。"
            )
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

    def _read_azimuths(self) -> tuple:
        resid, cmdid, length, _ = AEC_AZIMUTH_VALUES
        response = self.dev.ctrl_transfer(
            usb.util.CTRL_IN | usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_RECIPIENT_DEVICE,
            0, 0x80 | cmdid, resid, length + 1, self.TIMEOUT,
        )
        byte_data = response.tobytes()
        num_values = length // 4
        return struct.unpack("<" + "f" * num_values, byte_data[1:length + 1])

    def _read_and_cache(self) -> None:
        azimuths_rad = self._read_azimuths()
        auto_selected_rad = azimuths_rad[-1]
        deg = np.degrees(auto_selected_rad)
        if self.invert:
            deg = -deg
        deg = (deg + self.angle_offset) % 360
        with self._lock:
            self._last_angle = float(deg)

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._read_and_cache()
            except Exception:
                pass
            self._stop_event.wait(POLL_INTERVAL)

    def start(self) -> None:
        """バックグラウンドでの方向ポーリングを開始する。呼ばなければ従来通りestimate()呼び出し時に同期読み込みする。"""
        if not self._poll_thread.is_alive():
            self._read_and_cache_safe()  # 最初の値が入るまでestimate()が0度を返し続けないように
            self._poll_thread.start()

    def _read_and_cache_safe(self) -> None:
        try:
            self._read_and_cache()
        except Exception:
            pass

    def estimate(self, audio: np.ndarray) -> float:
        if self._poll_thread.is_alive():
            with self._lock:
                return self._last_angle
        # ポーリング未開始の場合は従来通り同期的に読む（後方互換）
        self._read_and_cache_safe()
        return self._last_angle

    def close(self):
        self._stop_event.set()
        if self._poll_thread.is_alive():
            self._poll_thread.join(timeout=POLL_INTERVAL * 3)
        usb.util.dispose_resources(self.dev)
