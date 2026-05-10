import { client, USE_MOCKS, getToken, API_BASE } from './client'
import { mock } from './mock'
import type { LogEntry } from './types'

export interface LogFilter {
  app_id?: string
  model?: string
  status?: string
  limit?: number
  since?: string
}

export async function listLogs(params: LogFilter = {}): Promise<LogEntry[]> {
  if (USE_MOCKS) return mock.listLogs(params)
  const { data } = await client.get<LogEntry[]>('/logs', { params })
  return data
}

/**
 * SSE-Stream connector. Returns an EventSource (real backend) or a polling-faker (mock).
 * `onMessage` ist die Callback-Funktion für jedes neue LogEntry.
 * Rückgabe: Cleanup-Funktion zum Schließen.
 */
export function streamLogs(onMessage: (entry: LogEntry) => void, onError?: (err: Event | Error) => void): () => void {
  if (USE_MOCKS) {
    // Fake stream: jede 2-4s ein neuer Eintrag
    let cancelled = false
    const tick = () => {
      if (cancelled) return
      onMessage(mock.nextStreamLog())
      setTimeout(tick, 2000 + Math.random() * 2000)
    }
    setTimeout(tick, 800)
    return () => { cancelled = true }
  }

  // Real SSE — Token via Query-Param weil EventSource keine custom headers kann
  const token = getToken() || ''
  const url = `${API_BASE}/logs/stream?token=${encodeURIComponent(token)}`
  const es = new EventSource(url)
  es.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data) as LogEntry
      onMessage(data)
    } catch (err) {
      console.warn('SSE parse error', err)
    }
  }
  es.onerror = (err) => {
    if (onError) onError(err)
  }
  return () => es.close()
}
