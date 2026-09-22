import { isJobView, type JobView } from './jobs'

export { isJobView, type JobView }

export interface JobEventHandlers {
  onJob(view: JobView): void
  onEnd(): void
  onError(error: Error): void
}

function parseJobView(event: Event): JobView | null {
  if (!(event instanceof MessageEvent)) {
    return null
  }
  const raw: unknown = event.data
  try {
    const parsed: unknown = typeof raw === 'string' ? JSON.parse(raw) : raw
    return isJobView(parsed) ? parsed : null
  } catch {
    return null
  }
}

/**
 * Subscribe to `GET /api/jobs/{id}/events` and return a cancel function.
 *
 * The stream closes itself on `end`; the browser reconnects on transient
 * errors, so only a definitively closed source is reported as an error.
 */
export function subscribeJobEvents(
  jobId: string,
  handlers: JobEventHandlers,
): () => void {
  const source = new EventSource('/api/jobs/' + jobId + '/events')
  let active = true
  const stop = () => {
    if (active) {
      active = false
      source.close()
    }
  }

  source.addEventListener('job', (event) => {
    if (!active) {
      return
    }
    const view = parseJobView(event)
    if (view === null) {
      handlers.onError(new Error('El servidor envió un estado de trabajo inválido.'))
      return
    }
    handlers.onJob(view)
  })
  source.addEventListener('end', () => {
    if (active) {
      stop()
      handlers.onEnd()
    }
  })
  source.addEventListener('error', () => {
    if (active && source.readyState === EventSource.CLOSED) {
      active = false
      handlers.onError(
        new Error('Se perdió la conexión con los eventos del trabajo.'),
      )
    }
  })

  return stop
}
