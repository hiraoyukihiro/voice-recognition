// PCのPythonサーバー(run.py)から字幕と方向を受け取る実装。
// reSpeaker XVF3000 → Python(文字起こし + 方向) → WebSocket(同じWi-Fi) → スマホ → G2画面 という流れ。
// sendPcmはG2マイクのデータだが、今はPCマイクを使うため受け取るだけで転送しない。

export interface SttSnapshot {
  finalText: string
  interimText: string
  finished: boolean
  direction?: number  // 音が来た方向（度数。0=正面、90=右、180=後ろ、270=左）
}

export interface SttClient {
  sendPcm(chunk: Uint8Array): void
  close(): void
}

export interface SttHandlers {
  // 声がしている間、約0.2秒ごとに届く方向（度数）
  onDirection?: (deg: number) => void
  // PCとつながった / 切れた
  onConnection?: (connected: boolean) => void
}

export function startSttStream(
  url: string,
  onSnapshot: (snap: SttSnapshot) => void,
  _onError?: (err: unknown) => void,
  handlers: SttHandlers = {},
): SttClient {
  let ws: WebSocket | null = null
  let closed = false

  // 現在の字幕状態を保持する
  let currentFinal = ''
  let currentInterim = ''
  let currentDirection: number | undefined = undefined

  function connect() {
    ws = new WebSocket(url)

    ws.onopen = () => {
      console.log('[stt] Pythonサーバーに接続しました')
      handlers.onConnection?.(true)
    }

    ws.onmessage = (event) => {
      let msg: Record<string, unknown>
      try {
        msg = JSON.parse(event.data as string)
      } catch {
        return
      }

      if (msg.type === 'direction') {
        if (typeof msg.direction === 'number') {
          currentDirection = msg.direction
          handlers.onDirection?.(msg.direction)
        }

      } else if (msg.type === 'subtitle') {
        const text = (msg.text as string) ?? ''
        const isFinal = msg.is_final !== false
        console.log('[stt] subtitle受信:', { text, isFinal, direction: msg.direction })
        if (msg.direction != null) currentDirection = msg.direction as number

        if (isFinal) {
          currentFinal = text
          currentInterim = ''
        } else {
          currentInterim = text
        }

        onSnapshot({
          finalText: currentFinal,
          interimText: currentInterim,
          finished: false,
          direction: currentDirection,
        })

      } else if (msg.type === 'subtitle_cancel') {
        currentInterim = ''
        onSnapshot({
          finalText: currentFinal,
          interimText: '',
          finished: false,
          direction: currentDirection,
        })

      } else if (msg.type === 'correction') {
        const text = (msg.text as string) ?? ''
        if (msg.direction != null) currentDirection = msg.direction as number
        currentFinal = text
        onSnapshot({
          finalText: currentFinal,
          interimText: '',
          finished: false,
          direction: currentDirection,
        })
      }
    }

    ws.onerror = (e) => {
      // 再接続で自動回復するため、エラーはログだけ残してUIには通知しない
      console.error('[stt] WebSocketエラー（再接続します）:', e)
    }

    ws.onclose = () => {
      if (closed) return
      handlers.onConnection?.(false)
      console.log('[stt] 接続が切れました。3秒後に再接続します...')
      setTimeout(connect, 3000)
    }
  }

  connect()

  return {
    sendPcm(_chunk: Uint8Array) {},
    close() {
      closed = true
      ws?.close()
    },
  }
}
