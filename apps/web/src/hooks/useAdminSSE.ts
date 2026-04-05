/**
 * React hook для SSE подключения к admin panel.
 *
 * Подключается при монтировании, отключается при размонтировании.
 * Парсит SSE события и вызывает callback-и.
 * При обрыве соединения — exponential backoff reconnect (1s, 2s, 4s, ..., max 30s).
 * При успешном подключении backoff сбрасывается.
 */

import { useEffect, useRef } from 'react'
import { createAdminSSE } from '../api/adminApi'

export interface SSEHandlers {
  onHealth?: (data: unknown) => void
  onEvents?: (data: unknown) => void
  onRuns?: (data: unknown) => void
  onWorkers?: (data: unknown) => void
  onError?: (error: Event) => void
  onReconnect?: (attempt: number) => void
}

const INITIAL_DELAY_MS = 1000
const MAX_DELAY_MS = 30000

export function useAdminSSE(handlers: SSEHandlers, enabled = true) {
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers

  useEffect(() => {
    if (!enabled) return

    let sse: EventSource | null = null
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null
    let delayMs = INITIAL_DELAY_MS
    let attempt = 0
    let cancelled = false

    function connect() {
      if (cancelled) return

      sse = createAdminSSE()

      sse.addEventListener('health', (e) => {
        try {
          const data = JSON.parse((e as MessageEvent).data)
          handlersRef.current.onHealth?.(data)
        } catch { /* ignore parse errors */ }
      })

      sse.addEventListener('events', (e) => {
        try {
          const data = JSON.parse((e as MessageEvent).data)
          handlersRef.current.onEvents?.(data)
        } catch { /* ignore */ }
      })

      sse.addEventListener('runs', (e) => {
        try {
          const data = JSON.parse((e as MessageEvent).data)
          handlersRef.current.onRuns?.(data)
        } catch { /* ignore */ }
      })

      sse.addEventListener('workers', (e) => {
        try {
          const data = JSON.parse((e as MessageEvent).data)
          handlersRef.current.onWorkers?.(data)
        } catch { /* ignore */ }
      })

      sse.onopen = () => {
        // Успешное подключение — сброс backoff
        delayMs = INITIAL_DELAY_MS
        attempt = 0
      }

      sse.onerror = (error) => {
        handlersRef.current.onError?.(error)

        // EventSource закрыт навсегда (readyState === CLOSED) — reconnect вручную
        if (sse && sse.readyState === EventSource.CLOSED) {
          sse.close()
          sse = null

          if (!cancelled) {
            attempt++
            handlersRef.current.onReconnect?.(attempt)
            reconnectTimeout = setTimeout(connect, delayMs)
            delayMs = Math.min(delayMs * 2, MAX_DELAY_MS)
          }
        }
        // Если CONNECTING — EventSource сам пытается переподключиться
      }
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimeout) clearTimeout(reconnectTimeout)
      if (sse) sse.close()
    }
  }, [enabled])
}
