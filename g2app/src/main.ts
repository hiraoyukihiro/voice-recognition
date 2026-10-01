import {
  waitForEvenAppBridge,
  TextContainerProperty,
  CreateStartUpPageContainer,
  TextContainerUpgrade,
  OsEventTypeList,
} from '@evenrealities/even_hub_sdk'
import { startSttStream } from './asr/stt'
import {
  mountUi, setStatus, setTranscript, onTapButton, onReplayButton,
  onConnectButton, setUrl, setDirection,
} from './ui'

mountUi()

// 角度（0=正面、時計回り）を 8方向の矢印・日本語・度数 に変換する
const DIRECTIONS = [
  { arrow: '↑', name: '前' },
  { arrow: '↗', name: '右前' },
  { arrow: '→', name: '右' },
  { arrow: '↘', name: '右後ろ' },
  { arrow: '↓', name: '後ろ' },
  { arrow: '↙', name: '左後ろ' },
  { arrow: '←', name: '左' },
  { arrow: '↖', name: '左前' },
]

function directionOf(deg: number) {
  const d = ((deg % 360) + 360) % 360
  return { ...DIRECTIONS[Math.round(d / 45) % 8], deg: Math.round(d) }
}

function directionLabel(deg: number): string {
  const { arrow, deg: d } = directionOf(deg)
  return `${arrow} ${d}°`
}

// G2の一番上に出す方向の行。例:「→ 右から声 90°」
function directionHeadline(deg: number): string {
  const { arrow, name, deg: d } = directionOf(deg)
  return `${arrow} ${name}から声 ${d}°`
}

// 方向フィルタ設定
const LOCK_TOLERANCE = 45  // ±45度以内なら同じ方向とみなす
let lockedDirection: number | null = null
let lastDirection: number | undefined = undefined

function isInLockedDirection(direction?: number): boolean {
  if (lockedDirection === null) return true
  if (direction == null) return true
  const diff = Math.abs(direction - lockedDirection)
  return Math.min(diff, 360 - diff) <= LOCK_TOLERANCE
}

// 方向の行の状態。PCは声がしている間だけ方向を送ってくるので、
// しばらく届かなければ「静か」とみなす
const DIRECTION_STALE_MS = 1500
let pcConnected = false
let lastDirectionAt = 0

function headerLine(): string {
  if (!pcConnected) return '× PC未接続'
  if (lastDirection == null || Date.now() - lastDirectionAt > DIRECTION_STALE_MS) return '― 静か'
  return directionHeadline(lastDirection)
}

// 字幕履歴（最大3行）。★が付いた行は、流れて消えるまで★のまま
const MAX_HISTORY = 3
interface SubtitleLine { text: string; at: number; star: boolean }
const subtitleHistory: SubtitleLine[] = []
let lastAddedFinal = ''
let interimLine = ''

// メガネのタップ（またはスマホの「聞き取れなかった」）で、押した前後2秒に届いた字幕を★で囲む。
// 「前」はすでに届いている行に、「後」はこれから2秒以内に届く行に★を付ける
const STAR_WINDOW_MS = 2000
let starUntil = 0

function starActive(): boolean {
  return Date.now() <= starUntil
}

function addToHistory(text: string) {
  if (!text.trim()) return
  subtitleHistory.push({ text, at: Date.now(), star: starActive() })
  if (subtitleHistory.length > MAX_HISTORY) subtitleHistory.shift()
}

function showLine(line: SubtitleLine): string {
  return line.star ? `★${line.text}★` : line.text
}

function historyText(): string {
  return subtitleHistory.map(showLine).join('\n')
}

function interimText(): string {
  if (!interimLine) return ''
  return starActive() ? `★${interimLine}★` : interimLine
}

// G2に出す全文: 1行目=方向、2行目=区切り、3行目以降=字幕
function buildDisplay(): string {
  const lines = subtitleHistory.map(showLine)
  if (interimLine) lines.push(interimText())
  const body = lines.length > 0 ? lines.join('\n') : 'Listening…'
  // ★の受付中は、押したことが分かるように方向の行の先頭にも★を出す
  const header = (starActive() ? '★ ' : '') + headerLine()
  // 文字数上限に収めるときは、方向の行を残して字幕の古い方を削る
  return `${header}\n────────\n${body.slice(-(240 - header.length - 10))}`
}

function markStar() {
  const now = Date.now()
  for (const line of subtitleHistory) {
    if (now - line.at <= STAR_WINDOW_MS) line.star = true
  }
  starUntil = now + STAR_WINDOW_MS
  console.log('[★] 前後2秒の字幕に印を付けます')
  setTranscript(historyText(), interimText())
  scheduleGlassesRender()
}

// PC(run.py)のURL。スマホの画面で変えられ、次回のために覚えておく
const URL_KEY = 'g2.pcUrl'
const DEFAULT_URL = (import.meta.env.VITE_PC_WS_URL as string | undefined) ?? 'ws://192.168.0.116:8765'

// QRコードで読み込んだとき（PCから http://<PCのIP>:5173 で配信）は、
// 配信元のPC＝run.pyのPCなので、住所が変わっても自動で合わせる
function servedFromPc(): string | null {
  const { protocol, hostname } = window.location
  if (!protocol.startsWith('http') || !hostname || hostname === 'localhost') return null
  return `ws://${hostname}:8765`
}

function loadUrl(): string {
  const fromPc = servedFromPc()
  if (fromPc) return fromPc
  try { return localStorage.getItem(URL_KEY) || DEFAULT_URL } catch { return DEFAULT_URL }
}

function saveUrl(url: string) {
  try { localStorage.setItem(URL_KEY, url) } catch { /* 保存できなくても接続はできる */ }
}

const bridge = await waitForEvenAppBridge()

const transcript = new TextContainerProperty({
  xPosition: 0,
  yPosition: 0,
  width: 576,
  height: 288,
  borderWidth: 0,
  borderColor: 5,
  paddingLength: 4,
  containerID: 1,
  containerName: 'transcript',
  content: 'Listening…',
  isEventCapture: 1,
})

const created = await bridge.createStartUpPageContainer(
  new CreateStartUpPageContainer({ containerTotalNum: 1, textObject: [transcript] }),
)
if (created !== 0) {
  console.error('Failed to create startup page')
}

let lastRender = ''
let renderTimer: number | null = null

function scheduleGlassesRender() {
  if (renderTimer !== null) return
  renderTimer = window.setTimeout(async () => {
    renderTimer = null
    const content = buildDisplay()
    if (content === lastRender) return
    lastRender = content
    await bridge.textContainerUpgrade(
      new TextContainerUpgrade({
        containerID: 1,
        containerName: 'transcript',
        content,
      }),
    )
  }, 120)
}

function refreshDirection() {
  setDirection(headerLine())
  scheduleGlassesRender()
}

// 声が止まったら「静か」に戻すため、定期的に方向の行を見直す
window.setInterval(refreshDirection, 500)

function updateStatusBar() {
  if (!pcConnected) {
    setStatus('connecting', 'PCに接続中…（run.py を起動し、同じWi-Fiに）')
  } else if (lockedDirection !== null) {
    setStatus('paused', `${directionLabel(lockedDirection)} に固定中 · スワイプで解除`)
  } else {
    setStatus('listening', 'PC接続中 · タップで★ · スワイプで方向を固定 · ダブルタップで終了')
  }
}

let stt: ReturnType<typeof startSttStream> | null = null

function connectPc(url: string) {
  stt?.close()
  pcConnected = false
  updateStatusBar()
  refreshDirection()
  try {
    stt = startSttStream(
      url,
      ({ finalText, interimText: interim, direction }) => {
        if (direction != null) lastDirection = direction

        // 方向フィルタ：固定中かつ範囲外なら無視する
        if (!isInLockedDirection(direction)) return

        const dirLabel = direction != null ? `${directionLabel(direction)} ` : ''

        // 新しい確定字幕が届いたら履歴に追加する（★の受付中なら★付きで入る）
        if (finalText && finalText !== lastAddedFinal) {
          lastAddedFinal = finalText
          addToHistory(`${dirLabel}${finalText}`)
        }

        interimLine = interim ? `${dirLabel}${interim}` : ''
        // ブラウザ表示：履歴を final、途中経過を interim として渡す
        setTranscript(historyText(), interimText())
        scheduleGlassesRender()
      },
      err => {
        console.error('STT error:', err)
      },
      {
        onDirection: deg => {
          lastDirection = deg
          lastDirectionAt = Date.now()
          refreshDirection()
        },
        onConnection: connected => {
          pcConnected = connected
          updateStatusBar()
          refreshDirection()
        },
      },
    )
  } catch (err) {
    setStatus('error', (err as Error)?.message ?? 'PCへの接続に失敗しました')
    console.error('STT startup failed:', err)
  }
}

setUrl(loadUrl())
connectPc(loadUrl())

onConnectButton(url => {
  if (!/^wss?:\/\//.test(url)) {
    setStatus('error', 'URLは ws:// で始めてください（例 ws://192.168.1.23:8765）')
    return
  }
  saveUrl(url)
  connectPc(url)
})

// ブラウザ上のボタンからもタップ・終了・強調を操作できるようにする
onTapButton(() => toggleDirectionLock())

onReplayButton(() => markStar())


// スワイプ → 方向を固定 / 解除
function toggleDirectionLock() {
  if (!stt) return
  if (lockedDirection === null) {
    // 今の方向を固定する
    lockedDirection = lastDirection ?? 0
    console.log(`[方向固定] ${Math.round(lockedDirection)}°`)
  } else {
    // 固定を解除する
    lockedDirection = null
    console.log('[方向固定解除]')
  }
  updateStatusBar()
  scheduleGlassesRender()
}

let cleanedUp = false
function cleanup() {
  if (cleanedUp) return
  cleanedUp = true
  stt?.close()
  unsubscribe()
}

function eventTypeOf(envelope?: { eventType?: OsEventTypeList }): OsEventTypeList | null {
  if (!envelope) return null
  return envelope.eventType ?? OsEventTypeList.CLICK_EVENT
}

// 音はPCのreSpeakerで拾うので、G2のマイクはオンにしない（電池の節約）
const unsubscribe = bridge.onEvenHubEvent(event => {
  const sysType = eventTypeOf(event.sysEvent)
  const textType = eventTypeOf(event.textEvent)

  if (sysType === OsEventTypeList.DOUBLE_CLICK_EVENT || textType === OsEventTypeList.DOUBLE_CLICK_EVENT) {
    bridge.shutDownPageContainer(1)
    return
  }

  // タップ → 前後2秒の字幕を★で囲む
  if (sysType === OsEventTypeList.CLICK_EVENT || textType === OsEventTypeList.CLICK_EVENT) {
    markStar()
    return
  }

  // 上下どちらかにスワイプ → 方向を固定 / 解除
  const swiped = [sysType, textType].some(t =>
    t === OsEventTypeList.SCROLL_TOP_EVENT || t === OsEventTypeList.SCROLL_BOTTOM_EVENT)
  if (swiped) {
    toggleDirectionLock()
    return
  }

  if (sysType === OsEventTypeList.SYSTEM_EXIT_EVENT || sysType === OsEventTypeList.ABNORMAL_EXIT_EVENT) {
    cleanup()
  }
})

window.addEventListener('beforeunload', cleanup)
