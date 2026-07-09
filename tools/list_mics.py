"""接続中のマイク・スピーカー一覧を表示する。"""
import sounddevice as sd

print("=== 利用可能なオーディオデバイス ===\n")
devices = sd.query_devices()
for i, d in enumerate(devices):
    in_ch = d["max_input_channels"]
    out_ch = d["max_output_channels"]
    kind = []
    if in_ch > 0:
        kind.append(f"入力:{in_ch}ch")
    if out_ch > 0:
        kind.append(f"出力:{out_ch}ch")
    print(f"[{i:2d}] {d['name']}  ({', '.join(kind)})")

print()
default_in = sd.query_devices(kind="input")
default_out = sd.query_devices(kind="output")
print(f"デフォルト入力 : {default_in['name']}")
print(f"デフォルト出力 : {default_out['name']}")
print()
print("config.py の MIC_DEVICE_INDEX をここで確認したデバイス番号に変更できます。")
print("None のままにすると上記のデフォルト入力が使われます。")
