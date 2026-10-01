"""
Even Hub の .ehpk パッケージを展開する（中身のファイルを取り出す）。

使い方: python tools/ehpk_unpack.py <入力.ehpk> <出力フォルダ>

形式（2026-10 に evenhub-cli 0.1.14 の出力を調べて判明）:
  ヘッダ 20バイト: "EHPK", u16 ver, u16 ?, u32 ヘッダ長(=20), u32 レコード数, u32 0
  以降レコードが並ぶ。先頭 u32 の下位バイトで種類が分かる:
    0xE4 ファイル: u32 圧縮長, u32 元の長さ, 2バイト(属性), u16 名前長, 名前, zstd圧縮データ
    0xE5 フォルダ: 2バイト(属性), u16 名前長, 名前
    0xE3 署名など（末尾）: ここで終わり
  名前と圧縮データは、それぞれ先頭から "EVEN REALITIES" をくり返し XOR してある。
"""
import os
import struct
import sys

import zstandard

KEY = b"EVEN REALITIES"


def unxor(buf: bytes) -> bytes:
    return bytes(b ^ KEY[i % len(KEY)] for i, b in enumerate(buf))


def unpack(path: str, out_dir: str) -> list[str]:
    d = open(path, "rb").read()
    magic, _ver, _x, hdr_len, _count, _zero = struct.unpack("<4sHHIII", d[:20])
    if magic != b"EHPK":
        raise ValueError("EHPK ファイルではありません")
    off = hdr_len
    names = []
    while off + 4 <= len(d):
        kind = d[off]
        if kind == 0xE4:  # ファイル
            clen, _olen = struct.unpack("<II", d[off + 4:off + 12])
            nlen = struct.unpack("<H", d[off + 14:off + 16])[0]
            name = unxor(d[off + 16:off + 16 + nlen]).decode("utf-8")
            start = off + 16 + nlen
            data = zstandard.ZstdDecompressor().decompressobj().decompress(unxor(d[start:start + clen]))
            dest = os.path.join(out_dir, *name.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(data)
            names.append(name)
            off = start + clen
        elif kind == 0xE5:  # フォルダ
            nlen = struct.unpack("<H", d[off + 6:off + 8])[0]
            off += 8 + nlen
        else:  # 0xE3 署名など
            break
    return names


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    for n in unpack(sys.argv[1], sys.argv[2]):
        print(n)
