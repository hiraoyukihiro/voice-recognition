// WebSocket接続先（config.py の WEBSOCKET_PORT と合わせること）
const WS_URL = "ws://localhost:8765";
const MAX_LINES = 3;

// 8方向矢印。0=↑(前) 1=↗ 2=→(右) 3=↘ 4=↓(後) 5=↙ 6=←(左) 7=↖
const ARROWS = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"];

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

function addSubtitle(text, direction, isFinal = true) {
  let line = currentPendingLine;
  if (!line) {
    line = document.createElement("div");

    const arrow = document.createElement("span");
    arrow.className = "subtitle-arrow";

    const textSpan = document.createElement("span");
    textSpan.className = "subtitle-text";

    line.append(arrow, textSpan);
    subtitleArea.appendChild(line);

    while (subtitleArea.children.length > MAX_LINES) {
      subtitleArea.removeChild(subtitleArea.firstChild);
    }
  }

  line.className = `subtitle-line${isFinal ? "" : " pending"}`;
  line.querySelector(".subtitle-arrow").textContent = directionToArrow(direction);
  line.querySelector(".subtitle-text").textContent = text;

  currentPendingLine = isFinal ? null : line;
}

// ---- 接続状態表示 ----
const statusBadge = document.getElementById("status-badge");
function setStatus(msg) {
  statusBadge.textContent = msg;
}

// ---- WebSocket接続 ----
function connect() {
  const ws = new WebSocket(WS_URL);

  ws.onopen = () => setStatus("接続中");

  ws.onmessage = (e) => {
    let data;
    try {
      data = JSON.parse(e.data);
    } catch {
      return;
    }
    if (typeof data.text !== "string") return;
    const isFinal = data.is_final !== undefined ? !!data.is_final : true;
    addSubtitle(data.text, data.direction || 0, isFinal);
  };

  ws.onclose = () => {
    setStatus("切断中... 3秒後に再接続");
    setTimeout(connect, 3000);
  };

  ws.onerror = () => ws.close();
}

// ---- 起動 ----
connect();
