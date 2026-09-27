"""このPCの同じWi-Fi内でのIPアドレスを1行で出す（G2起動.bat が使う）。"""
import socket

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(("8.8.8.8", 80))  # 実際には通信しない。どの出口を使うかを調べるだけ
    print(s.getsockname()[0])
except OSError:
    print("127.0.0.1")
finally:
    s.close()
