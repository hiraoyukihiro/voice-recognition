// HoloSound論文Figure 1の画面を再現する表示係。
// Python側から届く4種類のお知らせを、それぞれの担当に振り分けるだけの役目。
//   config      … 表示の決まり事（分割数・最大音源数など）。接続時に1回だけ届く
//   subtitle    … 字幕（is_final=false は認識途中）
//   sound_event … 声以外の音を1件検知した
//   direction   … 今どっちから音がしているか（0.2秒ごと）
const WS_URL = "ws://localhost:8765";

// Python側(config.py)から上書きされる。ここは通信前の仮の値。
let settings = {
  sectors: 12,
  max_sources: 4,
  sound_history: 3,
  arc_lifetime: 3.0,
  subtitle_lines: 3,
  subtitle_view: "subtitles",
};

// 8方向矢印。0=↑(前) 1=↗ 2=→(右) 3=↘ 4=↓(後) 5=↙ 6=←(左) 7=↖
const ARROWS = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"];

function directionToArrow(deg) {
  return ARROWS[(((Math.round(deg / 45) % 8) + 8) % 8)];
}

// 論文2.3節: 連続した角度を12個の区分に丸めてから表示する。
// 生の角度をそのまま出すと、少し動くたびに図がちらついて読みにくいため。
function toSector(deg) {
  const n = settings.sectors;
  return (((Math.round(deg / (360 / n)) % n) + n) % n);
}

// ---------------- ① 字幕 ----------------
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

    while (subtitleArea.children.length > settings.subtitle_lines) {
      subtitleArea.removeChild(subtitleArea.firstChild);
    }
  }

  line.className = `subtitle-line${isFinal ? "" : " pending"}`;
  line.querySelector(".subtitle-arrow").textContent = directionToArrow(direction);
  line.querySelector(".subtitle-text").textContent = text;

  currentPendingLine = isFinal ? null : line;
  if (settings.subtitle_view === "windows") moveSubtitleTo(direction);
}

// あとから届く「書き直し」を反映する。
// Voskが即座に出した粗い字幕を、Whisperが聞き直した正しい文で置き換える。
// 直近の行をまとめて1行に差し替え、✓印で「これは確定版」だと分かるようにする。
function applyCorrection(text, direction) {
  currentPendingLine = null;
  subtitleArea.textContent = "";

  const line = document.createElement("div");
  line.className = "subtitle-line corrected";

  const mark = document.createElement("span");
  mark.className = "subtitle-arrow";
  mark.textContent = "✓" + directionToArrow(direction);

  const textSpan = document.createElement("span");
  textSpan.className = "subtitle-text";
  textSpan.textContent = text;

  line.append(mark, textSpan);
  subtitleArea.appendChild(line);
}

// 認識中だった行を取り消して消す。
// Python側が「やっぱりこれは雑音だった」と判断した時に呼ばれる。
// これがないと、途中経過として出した字幕が画面に残りっぱなしになる。
function cancelPendingSubtitle() {
  if (!currentPendingLine) return;
  currentPendingLine.remove();
  currentPendingLine = null;
}

// windowsビュー: 論文では話者の上に字幕を置く。ここはARではないので、
// 「話している方向」を字幕の左右位置で表す近似にする。
function moveSubtitleTo(deg) {
  const rad = (deg * Math.PI) / 180;
  const x = Math.sin(rad);              // -1(左) 〜 +1(右)
  const y = Math.max(0, -Math.cos(rad)); // 0(前) 〜 1(真後ろ)
  subtitleArea.style.transform =
    `translateX(calc(-50% + ${(x * 26).toFixed(1)}vw)) translateY(${(y * 22).toFixed(1)}vh)`;
}

const viewBadge = document.getElementById("view-badge");

function applyView() {
  const windows = settings.subtitle_view === "windows";
  subtitleArea.classList.toggle("windows", windows);
  if (!windows) subtitleArea.style.transform = "";
  viewBadge.textContent = `表示: ${settings.subtitle_view}（Vキーで切替）`;
}

document.addEventListener("keydown", (e) => {
  if (e.key === "v" || e.key === "V") {
    settings.subtitle_view = settings.subtitle_view === "windows" ? "subtitles" : "windows";
    applyView();
  }
});

// ---------------- ② 方向の円弧 ----------------
const arcLayer = document.getElementById("arc-layer");
const CX = 200, CY = 200, R = 150;

// 区分ごとに「最後に音がした時刻」を覚えておき、古いものから消していく。
// これで論文の「同時に最大4音源」を再現する。
const sources = new Map(); // sector -> { time, kind }

function markSource(deg, kind) {
  sources.set(toSector(deg), { time: performance.now(), kind });
}

// 円周上の点を求める。0度=真上(前)、時計回り。SVGはy軸が下向きなのでcosを引く。
function pointOnCircle(deg, r) {
  const rad = (deg * Math.PI) / 180;
  return [CX + r * Math.sin(rad), CY - r * Math.cos(rad)];
}

function arcPath(centerDeg, spanDeg) {
  const [x1, y1] = pointOnCircle(centerDeg - spanDeg / 2, R);
  const [x2, y2] = pointOnCircle(centerDeg + spanDeg / 2, R);
  return `M ${x1.toFixed(1)} ${y1.toFixed(1)} A ${R} ${R} 0 0 1 ${x2.toFixed(1)} ${y2.toFixed(1)}`;
}

function renderArcs() {
  const now = performance.now();
  const lifetime = settings.arc_lifetime * 1000;

  for (const [sector, info] of sources) {
    if (now - info.time > lifetime) sources.delete(sector);
  }

  // 新しい音源から順に、最大 max_sources 個だけ描く（論文2.3節）
  const shown = [...sources.entries()]
    .sort((a, b) => b[1].time - a[1].time)
    .slice(0, settings.max_sources);

  arcLayer.textContent = "";
  const span = 360 / settings.sectors;
  for (const [sector, info] of shown) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", arcPath(sector * span, span * 0.8));
    path.setAttribute("class", `arc ${info.kind}`);
    // 時間が経つほど薄くして、音が止まったことが分かるようにする
    path.setAttribute("opacity", (1 - (now - info.time) / lifetime).toFixed(2));
    arcLayer.appendChild(path);
  }
  requestAnimationFrame(renderArcs);
}
requestAnimationFrame(renderArcs);

// ---------------- ③ 音の種類（直近3件） ----------------
const soundArea = document.getElementById("sound-area");

function addSoundEvent(ev) {
  const card = document.createElement("div");
  card.className = "sound-card";
  card.innerHTML = `
    <span class="sound-icon"></span>
    <span class="sound-dir"></span>
    <span class="sound-name"></span>
    <span class="sound-conf"></span>`;
  card.querySelector(".sound-icon").textContent = ev.icon || "🔊";
  card.querySelector(".sound-dir").textContent = directionToArrow(ev.direction || 0);
  card.querySelector(".sound-name").textContent = ev.name || "";
  card.querySelector(".sound-conf").textContent =
    `${Math.round((ev.confidence || 0) * 100)}%`;

  soundArea.appendChild(card);
  while (soundArea.children.length > settings.sound_history) {
    soundArea.removeChild(soundArea.firstChild);
  }
  // 古いものは薄くして、今鳴っている音との区別をつける
  [...soundArea.children].forEach((el, i, all) => {
    el.classList.toggle("stale", i < all.length - 1);
  });
}

// ---------------- 接続 ----------------
const statusBadge = document.getElementById("status-badge");

function setStatus(msg) {
  statusBadge.textContent = msg;
}

function handle(data) {
  switch (data.type) {
    case "config":
      settings = { ...settings, ...data };
      applyView();
      break;

    case "subtitle_cancel":
      cancelPendingSubtitle();
      break;

    case "correction":
      if (typeof data.text === "string" && data.text) {
        applyCorrection(data.text, data.direction || 0);
        markSource(data.direction || 0, "speech");
      }
      break;

    case "sound_event":
      addSoundEvent(data);
      markSource(data.direction || 0, "sound");
      break;

    case "direction":
      markSource(data.direction || 0, "sound");
      break;

    case "subtitle":
    default:
      if (typeof data.text !== "string") return;
      addSubtitle(data.text, data.direction || 0,
                  data.is_final !== undefined ? !!data.is_final : true);
      markSource(data.direction || 0, "speech");
  }
}

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
    handle(data);
  };

  ws.onclose = () => {
    setStatus("切断中... 3秒後に再接続");
    setTimeout(connect, 3000);
  };

  ws.onerror = () => ws.close();
}

applyView();
connect();
