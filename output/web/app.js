// WebSocket接続先（config.py の WEBSOCKET_PORT と合わせること）
const WS_URL = "ws://localhost:8765";
const MAX_LINES = 3;
const THEME_KEY = "display_theme_mode"; // "auto" | "light" | "dark"

const SPEAKER_MARKS = ["A", "B", "C", "D", "E", "F"];
const SPEAKER_CLASSES = ["spk-a", "spk-b", "spk-c", "spk-d", "spk-e", "spk-f"];

// 8方向矢印。index = round(direction/45) を 8 で正規化した値。
// 0=↑(前) 1=↗ 2=→(右) 3=↘ 4=↓(後) 5=↙ 6=←(左) 7=↖
const ARROWS = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"];

let ws = null;
let demoTimer = null;
let suppressReconnect = false;

// ---- 話者番号の正規化 ----
// speaker_id は将来的に数値(0-5)想定。旧バックエンド互換で "speaker_1" のような
// 文字列が来た場合は末尾の数値から算出する。
function normalizeSpeakerIndex(speakerId) {
  if (typeof speakerId === "number" && Number.isFinite(speakerId)) {
    return ((speakerId % 6) + 6) % 6;
  }
  const match = String(speakerId).match(/(\d+)/);
  if (match) {
    const n = parseInt(match[1], 10) - 1;
    return ((n % 6) + 6) % 6;
  }
  return 0;
}

function directionToArrow(deg) {
  const idx = (((Math.round(deg / 45) % 8) + 8) % 8);
  return ARROWS[idx];
}

// ---- 字幕描画 ----
const subtitleArea = document.getElementById("subtitle-area");

// 認識中（未確定）の行はこの変数が指す1行を書き換え続け、確定したら null に戻す。
// これにより「今日」「今日の」「今日の授業」のように部分認識結果が変化するたびに
// 別々の行として積み上がるのを防ぐ（1つの発話は1行のまま伸びていく）。
let currentPendingLine = null;

function addSubtitle(speakerId, text, direction, isFinal = true) {
  const spkIdx = normalizeSpeakerIndex(speakerId);
  const arrowChar = directionToArrow(direction);

  let line = currentPendingLine;
  if (!line) {
    subtitleArea.querySelectorAll(".subtitle-line.active")
      .forEach((el) => el.classList.remove("active"));

    line = document.createElement("div");

    const dot = document.createElement("span");
    dot.className = "subtitle-dot";

    const mark = document.createElement("span");
    mark.className = "subtitle-speaker-mark";

    const arrow = document.createElement("span");
    arrow.className = "subtitle-arrow";

    const textSpan = document.createElement("span");
    textSpan.className = "subtitle-text";

    line.append(dot, mark, arrow, textSpan);
    subtitleArea.appendChild(line);

    while (subtitleArea.children.length > MAX_LINES) {
      subtitleArea.removeChild(subtitleArea.firstChild);
    }
  }

  line.className = `subtitle-line active ${SPEAKER_CLASSES[spkIdx]}${isFinal ? "" : " pending"}`;
  line.querySelector(".subtitle-speaker-mark").textContent = SPEAKER_MARKS[spkIdx];
  line.querySelector(".subtitle-arrow").textContent = arrowChar;
  line.querySelector(".subtitle-text").textContent = text;

  currentPendingLine = isFinal ? null : line;
}

// ---- コンパス ----
const needle = document.getElementById("compass-needle");

function updateCompass(deg) {
  needle.style.transform = `translate(-50%, -100%) rotate(${deg}deg)`;
}

// ---- 接続状態表示 ----
const statusBadge = document.getElementById("status-badge");
function setStatus(msg) {
  statusBadge.textContent = msg;
}

// ---- WebSocket接続 ----
function connect() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    setStatus("接続中");
    stopDemo();
  };

  ws.onmessage = (e) => {
    let data;
    try {
      data = JSON.parse(e.data);
    } catch {
      return;
    }
    if (typeof data.text !== "string") return;
    const isFinal = data.is_final !== undefined ? !!data.is_final : true;
    updateCompass(data.direction || 0);
    addSubtitle(data.speaker_id, data.text, data.direction || 0, isFinal);
  };

  ws.onclose = () => {
    if (suppressReconnect) {
      suppressReconnect = false;
      return;
    }
    setStatus("切断中... 3秒後に再接続");
    setTimeout(connect, 3000);
  };

  ws.onerror = () => ws.close();
}

// ---- テーマ（自動/ライト/ダーク） ----
const themeToggleBtn = document.getElementById("theme-toggle");
const THEME_LABELS = { auto: "自動", light: "ライト", dark: "ダーク" };
const darkMediaQuery = window.matchMedia("(prefers-color-scheme: dark)");

function resolveTheme(mode) {
  if (mode === "auto") {
    return darkMediaQuery.matches ? "dark" : "light";
  }
  return mode;
}

function applyThemeMode(mode) {
  document.documentElement.dataset.theme = resolveTheme(mode);
  themeToggleBtn.textContent = THEME_LABELS[mode];
  localStorage.setItem(THEME_KEY, mode);
}

function currentThemeMode() {
  return localStorage.getItem(THEME_KEY) || "auto";
}

themeToggleBtn.addEventListener("click", () => {
  const order = ["auto", "light", "dark"];
  const next = order[(order.indexOf(currentThemeMode()) + 1) % order.length];
  applyThemeMode(next);
});

darkMediaQuery.addEventListener("change", () => {
  if (currentThemeMode() === "auto") {
    applyThemeMode("auto");
  }
});

// ---- デモ/シミュレーターモード ----
// 実機・バックエンド未接続でもPCブラウザで見た目を確認できるようにする
const demoSamples = [
  { speaker_id: 0, text: "わかりました、次の議題に移りましょう", direction: -45 },
  { speaker_id: 1, text: "明日の会議は10時からで問題ないですか", direction: 45 },
  { speaker_id: 2, text: "資料は事前に共有してもらえますか", direction: 0 },
  { speaker_id: 0, text: "承知しました、準備しておきます", direction: -90 },
  { speaker_id: 3, text: "私からも一点よろしいでしょうか", direction: 135 },
];

function startDemo() {
  let i = 0;
  setStatus("シミュレーターモード");
  const tick = () => {
    const s = demoSamples[i % demoSamples.length];
    updateCompass(s.direction);
    addSubtitle(s.speaker_id, s.text, s.direction, true);
    i++;
    demoTimer = setTimeout(tick, 2200);
  };
  tick();
}

function stopDemo() {
  if (demoTimer) {
    clearTimeout(demoTimer);
    demoTimer = null;
  }
}

const demoToggleBtn = document.getElementById("demo-toggle");
demoToggleBtn.addEventListener("click", () => {
  if (demoTimer) {
    stopDemo();
    connect();
  } else {
    if (ws) {
      suppressReconnect = true;
      ws.close();
    }
    startDemo();
  }
});

// ---- 起動 ----
applyThemeMode(currentThemeMode());
updateCompass(0);
connect();
