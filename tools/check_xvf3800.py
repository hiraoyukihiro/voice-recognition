"""
reSpeaker XVF3800 接続確認スクリプト。
USB制御インターフェース（DOA取得用）とオーディオ入力デバイスの両方を確認する。

使い方: python tools/check_xvf3800.py
"""
import sys
import os

import sounddevice as sd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from processing.direction.xvf3800_doa import XVF3800DOA, VENDOR_ID, PRODUCT_ID

print("=== 1. USB制御インターフェース確認 ===")
try:
    doa = XVF3800DOA()
    print(f"OK: デバイスを検出しました (VID=0x{VENDOR_ID:04X}, PID=0x{PRODUCT_ID:04X})")
    print("\n5秒間、DOA角度を読み取ります。マイクアレイに向かって話しかけてください。")
    import time
    for _ in range(10):
        angle = doa.estimate(None)
        print(f"  DOA角度: {angle:6.1f}°")
        time.sleep(0.5)
    doa.close()
except RuntimeError as e:
    print(f"NG: {e}")
    print("  → USBケーブルの接続、Windowsのデバイス認識状況を確認してください。")

print("\n=== 2. オーディオ入力デバイス確認 ===")
found = False
for i, d in enumerate(sd.query_devices()):
    name = d["name"]
    if d["max_input_channels"] > 0:
        marker = ""
        if any(k in name for k in ("ReSpeaker", "XVF", "XMOS")):
            marker = "  ← これがreSpeakerと思われます"
            found = True
        print(f"[{i:2d}] {name}  (入力:{d['max_input_channels']}ch){marker}")

if found:
    print("\nOK: reSpeakerのオーディオ入力を検出しました。")
    print("  config.py の MIC_DEVICE_INDEX を上記の番号に設定してください。")
else:
    print("\nNG: reSpeakerらしきオーディオ入力デバイスが見つかりません。")
    print("  → USB接続後、少し待ってから再実行してください。")
