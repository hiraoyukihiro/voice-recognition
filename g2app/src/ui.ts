type Status = 'connecting' | 'listening' | 'paused' | 'error'

let statusEl: HTMLDivElement
let finalEl: HTMLSpanElement
let interimEl: HTMLSpanElement
let tapBtn: HTMLButtonElement
let replayBtn: HTMLButtonElement
let urlInput: HTMLInputElement
let urlBtn: HTMLButtonElement
let dirEl: HTMLDivElement

export function mountUi() {
  const app = document.querySelector<HTMLDivElement>('#app')!
  app.innerHTML = `
    <main class="panel">
      <header>
        <h1>G2 方向+字幕</h1>
        <div id="status" class="status status-connecting">Connecting…</div>
      </header>
      <div class="pc-bar">
        <label for="pc-url">PCのURL</label>
        <input id="pc-url" type="text" inputmode="url" autocapitalize="off" autocorrect="off" spellcheck="false" />
        <button id="pc-connect" class="sim-btn">接続</button>
      </div>
      <div id="direction" class="direction">― 方向待ち</div>
      <section class="transcript" aria-live="polite">
        <span id="final"></span><span id="interim" class="interim"></span>
      </section>
      <div class="sim-bar">
        <button id="btn-tap" class="sim-btn">👆 タップ（方向を固定 / 解除）</button>
        <button id="btn-replay" class="sim-btn sim-btn-replay">❓ 聞き取れなかった</button>
      </div>
    </main>
  `
  statusEl = app.querySelector<HTMLDivElement>('#status')!
  finalEl  = app.querySelector<HTMLSpanElement>('#final')!
  interimEl = app.querySelector<HTMLSpanElement>('#interim')!
  tapBtn    = app.querySelector<HTMLButtonElement>('#btn-tap')!
  replayBtn = app.querySelector<HTMLButtonElement>('#btn-replay')!
  urlInput  = app.querySelector<HTMLInputElement>('#pc-url')!
  urlBtn    = app.querySelector<HTMLButtonElement>('#pc-connect')!
  dirEl     = app.querySelector<HTMLDivElement>('#direction')!
  injectStyles()
}

export function onTapButton(cb: () => void) {
  tapBtn?.addEventListener('click', cb)
}

export function onReplayButton(cb: () => void) {
  replayBtn?.addEventListener('click', cb)
}

// 「接続」ボタンで、入力されたURLを渡す
export function onConnectButton(cb: (url: string) => void) {
  urlBtn?.addEventListener('click', () => cb(urlInput.value.trim()))
}

export function setUrl(url: string) {
  if (urlInput) urlInput.value = url
}

export function setDirection(text: string) {
  if (dirEl) dirEl.textContent = text
}


export function setStatus(kind: Status, text: string) {
  if (!statusEl) return
  statusEl.className = `status status-${kind}`
  statusEl.textContent = text
}

export function setTranscript(finalText: string, interimText: string) {
  if (!finalEl) return
  finalEl.textContent = finalText
  interimEl.textContent = interimText
}

function injectStyles() {
  // ER brand dark-theme surfaces: #232323 / #2E2E2E / #3E3E3E.
  // ER OS green (#3CFA44) + signal red (#FF453A) for state chips.
  const css = `
    :root { color-scheme: dark; }
    html, body { margin: 0; height: 100%; background: #232323; color: #E5E5E5;
      font: 16px/1.4 -apple-system, BlinkMacSystemFont, 'Helvetica Neue', system-ui, sans-serif;
      touch-action: manipulation; -webkit-text-size-adjust: 100%;
      overscroll-behavior: none; }
    #app { display: flex; height: 100%; }
    .panel { display: flex; flex-direction: column; gap: 16px;
      width: 100%; max-width: 640px; margin: 0 auto; padding: 24px; box-sizing: border-box; }
    header { display: flex; align-items: center; justify-content: space-between; }
    h1 { font-size: 18px; font-weight: 600; margin: 0; letter-spacing: 0.02em; }
    .status { font-size: 12px; padding: 4px 10px; border-radius: 999px;
      border: 1px solid transparent; letter-spacing: 0.04em; text-transform: uppercase; }
    .status-connecting { color: #A7A7A7; border-color: #3E3E3E; }
    .status-listening  { color: #3CFA44; border-color: #3CFA44; background: rgba(60,250,68,0.08); }
    .status-paused     { color: #E5E5E5; border-color: #7B7B7B; background: rgba(229,229,229,0.06); }
    .status-error      { color: #FF453A; border-color: #FF453A; background: rgba(255,69,58,0.08); }
    .transcript { flex: 1; overflow: auto; background: #2E2E2E; border: 1px solid #3E3E3E;
      color: #E5E5E5;
      border-radius: 12px; padding: 20px; font-size: 18px; line-height: 1.5;
      min-height: 180px; white-space: pre-wrap; word-break: break-word; }
    .interim { color: #919191; }
    .sim-bar { display: flex; gap: 12px; }
    .pc-bar { display: flex; gap: 8px; align-items: center; }
    .pc-bar label { font-size: 13px; color: #A7A7A7; white-space: nowrap; }
    .pc-bar input { flex: 1; min-width: 0; padding: 10px; border-radius: 8px;
      border: 1px solid #3E3E3E; background: #2E2E2E; color: #E5E5E5; font-size: 15px; }
    .pc-bar .sim-btn { flex: 0 0 auto; padding: 10px 16px; }
    .direction { font-size: 28px; font-weight: 600; text-align: center; padding: 8px;
      border-radius: 12px; background: #2E2E2E; border: 1px solid #3E3E3E; }
    .sim-btn { flex: 1; padding: 14px 8px; border-radius: 10px; border: 1px solid #3E3E3E;
      background: #2E2E2E; color: #E5E5E5; font-size: 15px; cursor: pointer;
      transition: background 0.15s; }
    .sim-btn:hover { background: #3E3E3E; }
    .sim-btn:active { background: #4E4E4E; }
    .sim-btn-replay { border-color: #FFD60A; color: #FFD60A; }
    .sim-btn-replay:hover { background: rgba(255,214,10,0.12); }
  `
  const style = document.createElement('style')
  style.textContent = css
  document.head.appendChild(style)
}
