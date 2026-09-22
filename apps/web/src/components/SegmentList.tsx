import { useEffect, useState } from 'react'

import { getSegments, type TranscriptSegment } from '../api/jobs'

interface SegmentListProps {
  transcriptId: string | null
  // S5.10: si existe, cada marca de tiempo se vuelve un botón que busca el
  // instante en el reproductor del original.
  onSeek?: (startMs: number) => void
}

type Outcome =
  | { phase: 'error'; message: string }
  | { phase: 'ready'; segments: TranscriptSegment[] }

interface Loaded {
  transcriptId: string
  outcome: Outcome
}

function formatTimestamp(ms: number): string {
  const total = Math.max(0, ms)
  const minutes = Math.floor(total / 60_000)
  const seconds = Math.floor((total % 60_000) / 1000)
  const tenths = Math.floor((total % 1000) / 100)
  return (
    String(minutes).padStart(2, '0') +
    ':' +
    String(seconds).padStart(2, '0') +
    '.' +
    String(tenths)
  )
}

function durationAttribute(ms: number): string {
  return 'PT' + (Math.max(0, ms) / 1000).toFixed(1) + 'S'
}

export function SegmentList({ transcriptId, onSeek }: SegmentListProps) {
  // El estado se asocia al id cargado; si no coincide con la prop, seguimos
  // cargando. Así el efecto nunca llama a setState de forma sincrónica.
  const [loaded, setLoaded] = useState<Loaded | null>(null)

  useEffect(() => {
    if (transcriptId === null) {
      return
    }

    const controller = new AbortController()

    void getSegments(transcriptId, controller.signal)
      .then((segments) => {
        setLoaded({ transcriptId, outcome: { phase: 'ready', segments } })
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }
        setLoaded({
          transcriptId,
          outcome: {
            phase: 'error',
            message:
              error instanceof Error
                ? error.message
                : 'No se pudieron cargar los segmentos.',
          },
        })
      })

    return () => {
      controller.abort()
    }
  }, [transcriptId])

  if (transcriptId === null) {
    return null
  }

  const state: Outcome | { phase: 'loading' } =
    loaded !== null && loaded.transcriptId === transcriptId
      ? loaded.outcome
      : { phase: 'loading' }

  return (
    <section className="segments-card" aria-labelledby="segments-title">
      <div className="card-heading">
        <div>
          <p className="section-kicker">TEXTO</p>
          <h2 id="segments-title">Segmentos</h2>
        </div>
      </div>

      {state.phase === 'loading' ? (
        <p className="empty-state" role="status">
          Cargando la transcripción…
        </p>
      ) : state.phase === 'error' ? (
        <p className="job-error" role="alert">
          {state.message}
        </p>
      ) : state.segments.length === 0 ? (
        <p className="empty-state">La transcripción no contiene segmentos.</p>
      ) : (
        // ponytail: sin virtualizar, S5.15
        <ol className="segments">
          {state.segments.map((segment) => {
            const timestamp = (
              <time dateTime={durationAttribute(segment.start_ms)}>
                {formatTimestamp(segment.start_ms) +
                  ' → ' +
                  formatTimestamp(segment.end_ms)}
              </time>
            )
            return (
              <li key={segment.id}>
                {onSeek ? (
                  <button
                    type="button"
                    className="segment-seek"
                    onClick={() => {
                      onSeek(segment.start_ms)
                    }}
                    aria-label={
                      'Reproducir desde ' + formatTimestamp(segment.start_ms)
                    }
                  >
                    {timestamp}
                  </button>
                ) : (
                  timestamp
                )}
                <p className="segment-text">{segment.text}</p>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
