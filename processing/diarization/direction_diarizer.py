"""
方向(DOA)ベースの話者分離。
「誰なのか」ではなく「さっきと違う方向から聞こえた」という区別だけを行う。
声の特徴量計算（resemblyzer/pyannote）が不要になるため軽量で、
pyannoteのような数百秒単位のフリーズも起きない
（先生の引き継ぎ資料 why-we-changed.pdf の提案）。

弱点（分かった上で使うこと）:
- 同じ方向にいる2人は区別できない（隣同士だと同じ色になる）
- その人が移動すると別人だと思われる
- はねかえりの多い部屋（体育館など）では方向がぶれる

方向は円環（0度と359度は隣り合っている）なので、単純な引き算・平均は使えない。
"""
import math


def circular_diff(a: float, b: float) -> float:
    """2つの角度(0〜360度)の最短差(0〜180度)を返す。359度と1度は2度になる。"""
    d = abs(a - b) % 360
    return min(d, 360 - d)


def circular_ema(old_deg: float, new_deg: float, rate: float) -> float:
    """
    角度の指数移動平均。単位ベクトルに変換してから平均し、角度に戻す。
    そのまま (1-rate)*old + rate*new のように角度を直接平均すると、
    358度と2度のような0度またぎのケースで真逆に近い値になってしまうため。
    """
    old_rad, new_rad = math.radians(old_deg), math.radians(new_deg)
    x = (1 - rate) * math.cos(old_rad) + rate * math.cos(new_rad)
    y = (1 - rate) * math.sin(old_rad) + rate * math.sin(new_rad)
    return math.degrees(math.atan2(y, x)) % 360


class DirectionDiarizer:
    """
    angle_tolerance以内の方向差なら同一話者、それより離れていれば新しい話者として登録する。
    max_speakersに達したら、それ以降は最も近い既存話者に割り当てる（表示側が6色までのため）。
    """

    def __init__(self, angle_tolerance: float = 30.0, update_rate: float = 0.3, max_speakers: int = 6):
        self.angle_tolerance = angle_tolerance
        self.update_rate = update_rate
        self.max_speakers = max_speakers
        self._speaker_angles: dict[str, float] = {}
        self._speaker_count = 0

    def identify(self, direction_deg: float) -> str:
        best_id, best_diff = None, 361.0
        for spk_id, angle in self._speaker_angles.items():
            diff = circular_diff(direction_deg, angle)
            if diff < best_diff:
                best_diff = diff
                best_id = spk_id

        if best_id is not None and best_diff <= self.angle_tolerance:
            # 同一話者とみなし、登録角度を少しずつ現在の方向に近づける
            self._speaker_angles[best_id] = circular_ema(
                self._speaker_angles[best_id], direction_deg, self.update_rate
            )
            return best_id

        if self._speaker_count < self.max_speakers:
            self._speaker_count += 1
            new_id = f"speaker_{self._speaker_count}"
            self._speaker_angles[new_id] = direction_deg
            print(f"[DirectionDiarizer] 新しい話者を検出: {new_id} ({direction_deg:.0f}度)")
            return new_id

        # 最大話者数に達している場合は、最も近い既存話者に割り当てる
        return best_id if best_id is not None else "speaker_1"
