"""
HoloSound論文で使われた「DHH（耳が聞こえない・聞こえにくい人）が知りたい音 19種類」の定義。

論文本文には19種の全リストは載っていない（例として door knock / fire alarm / phone ring のみ）。
そのため、論文が下敷きにしたHomeSound[16]の対象音と、論文が挙げた例をもとに19種を構成した。

各クラスは AudioSet（PANNsが判定できる527種のラベル集合）の
どのラベルに当たるかを `audioset` に列挙する。判定時はこの中の最大スコアを
そのクラスのスコアとして扱う（例: 「サイレン」は救急車でもパトカーでも成立させる）。

対象を19種に絞る理由は論文2.2節と同じで、生活上重要な音だけを出し、
画面を情報で埋めないため。増やしたい場合はこのリストに足すだけでよい。
"""

# key   : 内部用の識別子（英数字）
# ja    : 画面に出す日本語名
# icon  : 画面に出す絵文字
# audioset: AudioSetラベル名（panns_inference の labels と完全一致する文字列であること）
SOUND_CLASSES = [
    {"key": "knock",       "ja": "ノックの音",     "icon": "🚪", "audioset": ["Knock"]},
    {"key": "doorbell",    "ja": "インターホン",   "icon": "🔔", "audioset": ["Doorbell", "Ding-dong", "Ding", "Chime"]},
    {"key": "door",        "ja": "ドアの開閉",     "icon": "🚪", "audioset": ["Door", "Sliding door", "Slam"]},
    {"key": "fire_alarm",  "ja": "火災報知器",     "icon": "🔥", "audioset": ["Fire alarm", "Smoke detector, smoke alarm"]},
    {"key": "alarm",       "ja": "アラーム音",     "icon": "⏰", "audioset": ["Alarm clock", "Alarm", "Beep, bleep", "Buzzer", "Reversing beeps"]},
    {"key": "phone",       "ja": "電話の着信",     "icon": "📞", "audioset": ["Telephone bell ringing", "Ringtone", "Telephone"]},
    {"key": "microwave",   "ja": "電子レンジ",     "icon": "🍱", "audioset": ["Microwave oven"]},
    {"key": "boiling",     "ja": "お湯・やかん",   "icon": "🫖", "audioset": ["Boiling", "Steam", "Steam whistle"]},
    {"key": "water",       "ja": "水の音",         "icon": "🚿", "audioset": ["Water tap, faucet", "Sink (filling or washing)", "Toilet flush", "Water"]},
    {"key": "appliance",   "ja": "掃除機・家電",   "icon": "🧹", "audioset": ["Vacuum cleaner", "Blender", "Electric shaver, electric razor", "Hair dryer"]},
    {"key": "dishes",      "ja": "食器の音",       "icon": "🍽️", "audioset": ["Dishes, pots, and pans", "Cutlery, silverware", "Glass", "Shatter"]},
    {"key": "baby_cry",    "ja": "赤ちゃんの泣き声", "icon": "👶", "audioset": ["Baby cry, infant cry", "Crying, sobbing"]},
    {"key": "dog",         "ja": "犬の鳴き声",     "icon": "🐕", "audioset": ["Bark", "Dog", "Howl"]},
    {"key": "cat",         "ja": "猫の鳴き声",     "icon": "🐈", "audioset": ["Meow", "Cat"]},
    {"key": "car_horn",    "ja": "クラクション",   "icon": "🚗", "audioset": ["Vehicle horn, car horn, honking", "Air horn, truck horn", "Car alarm"]},
    {"key": "siren",       "ja": "サイレン",       "icon": "🚨", "audioset": ["Siren", "Civil defense siren", "Ambulance (siren)", "Police car (siren)", "Fire engine, fire truck (siren)"]},
    {"key": "footsteps",   "ja": "足音",           "icon": "👣", "audioset": ["Walk, footsteps"]},
    {"key": "applause",    "ja": "拍手",           "icon": "👏", "audioset": ["Applause", "Clapping"]},
    {"key": "laughter",    "ja": "笑い声",         "icon": "😄", "audioset": ["Laughter", "Belly laugh", "Giggle", "Chuckle, chortle"]},
]

# 「人の声」は字幕係が担当するので、音イベントとしては出さない（論文2.2節: non-speech sounds）。
SPEECH_LABELS = [
    "Speech",
    "Male speech, man speaking",
    "Female speech, woman speaking",
    "Child speech, kid speaking",
    "Conversation",
    "Narration, monologue",
    "Hubbub, speech noise, speech babble",
]


def find_unknown_labels(known_labels) -> list:
    """
    上の表に書いたAudioSetラベル名のうち、実際のAudioSetに存在しないものを返す。
    タイプミスを黙って見逃すと「そのクラスだけ永久に反応しない」という
    気づきにくい不具合になるため、起動時に必ず検査する。
    """
    known = set(known_labels)
    unknown = []
    for cls in SOUND_CLASSES:
        for name in cls["audioset"]:
            if name not in known:
                unknown.append(f'{cls["key"]}: {name}')
    for name in SPEECH_LABELS:
        if name not in known:
            unknown.append(f"speech: {name}")
    return unknown
