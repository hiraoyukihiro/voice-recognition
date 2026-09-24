"""
reSpeaker XVF3000 (Mic Array v2.0) 接続確認スクリプト。
Zadig でドライバを入れたあと、方向（DOA角度）が読めるかを自分の目で確かめる。

使い方: python tools/check_xvf3000.py
        Ctrl + C で終了
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from processing.direction.xvf3000_doa import XVF3000DOA, VENDOR_ID, PRODUCT_ID

NAMES = ["前", "右前", "右", "右後ろ", "後ろ", "左後ろ", "左", "左前"]
ARROWS = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]

print("=== XVF3000 方向チェック ===")
try:
    doa = XVF3000DOA()
except RuntimeError as e:
    print(f"NG: {e}")
    print("  → Entity not found なら Zadig の手順をやり直してください"
          "（SEEED Control (Interface 3) / USB ID 2886 0018 03 / WinUSB）。")
    print("  → 見つかりません なら USBケーブルと挿し口を確認してください。")
    sys.exit(1)

print(f"OK: 方向を読めました (VID=0x{VENDOR_ID:04X}, PID=0x{PRODUCT_ID:04X})")
print("マイクのまわりを歩きながら話しかけてください。声がすると「声あり」になります。")
print("Ctrl + C で終了します。\n")

try:
    while True:
        deg = doa.estimate(None)
        i = round(deg / 45) % 8
        voice = "声あり" if doa.is_voice() else "  -   "
        print(f"\r  {ARROWS[i]} {NAMES[i]:<4} {deg:5.0f}°   {voice}   ", end="", flush=True)
        time.sleep(0.2)
except KeyboardInterrupt:
    print("\n終了しました。")
finally:
    doa.close()
