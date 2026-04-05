/**
 * React hook для SSE подключения к admin panel.
 * Подключается при монтировании, отключается при размонтировании.
 * Парсит SSE события и вызывает callback-и.
 */

import { useEffect, useRef } from 'react'
import { createAdminSSE } from '../api/adminApi'

export interface SSEHandlers {
  onHealth?: (data: unknown) => void
  onEvents?: (data: unknown) => void
  onRuns?: (data: unknown) => void
  onWorkers?: (data: unknown) => void
  onError?: (error: Event) => void
}

export function useAdminSSE(handlers: SSEHandlers, enabled = true) {
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers

  useEffect(() => {
    if (!enabled) return

    const sse = createAdminSSE()

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

    sse.onerror = (error) => {
      handlersRef.current.onError?.(error)
    }

    return () => {
      sse.close()
    }
  }, [enabled])
}
