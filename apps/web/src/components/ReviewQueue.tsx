import { useState } from 'react'

import type { TranscriptSegment } from '../api/jobs'
import { flagLabel, flaggedSegments } from '../lib/qualityFlags'
import './ReviewQueue.css'

interface ReviewQueueProps {
  // Todos los segmentos de la transcripción; la cola toma los que tienen flags.
  segments: readonly TranscriptSegment[]
  onSelect: (segment: TranscriptSegment) => void
}

const ALL = 'all'

// S13.06: el estado "revisado" es local a la sesión (no se persiste; recargar
// la página lo reinicia). ponytail: persistirlo exige un contrato de API nuevo.
export function ReviewQueue({ segments, onSelect }: ReviewQueueProps) {
  const [reviewed, setReviewed] = useState<ReadonlySet<string>>(new Set())
  const [filter, setFilter] = useState(ALL)
  const [position, setPosition] = useState(0)

  const flagged = flaggedSegments(segments)
  const kinds = [...new Set(flagged.flatMap((s) => s.quality.flags))]
  const pending = flagged.filter(
    (segment) =>
      !reviewed.has(segment.id) &&
      (filter === ALL || segment.quality.flags.includes(filter)),
  )
  const index = Math.min(position, Math.max(0, pending.length - 1))
  const current = pending[index]
  const count = pending.length

  function go(next: number) {
    const target = pending[next]
    if (target) {
      setPosition(next)
      onSelect(target)
    }
  }

  function markReviewed() {
    if (!current) {
      return
    }
    setReviewed((previous) => new Set(previous).add(current.id))
    // El siguiente pendiente ocupa el mismo índice al salir el actual.
    const following = pending[index + 1] ?? pending[index - 1]
    if (following) {
      setPosition(index + 1 < count ? index : index - 1)
      onSelect(following)
    }
  }

  return (
    <section className="review-queue" aria-labelledby="review-title">
      <div className="review-heading">
        <h2 id="review-title">Revisión</h2>
        <span className="review-count" role="status">
          {count === 1
            ? '1 segmento por revisar'
            : count + ' segmentos por revisar'}
        </span>
      </div>

      {flagged.length === 0 ? (
        <p className="empty-state">Ningún segmento necesita revisión.</p>
      ) : (
        <>
          <label className="review-filter">
            Tipo
            <select
              value={filter}
              onChange={(event) => {
                setFilter(event.target.value)
                setPosition(0)
              }}
            >
              <option value={ALL}>Todos</option>
              {kinds.map((kind) => (
                <option key={kind} value={kind}>
                  {flagLabel(kind)}
                </option>
              ))}
            </select>
          </label>

          {current ? (
            <div className="review-current">
              <p className="review-flags">
                {current.quality.flags.map(flagLabel).join(' · ')}
              </p>
              <p className="review-text">{current.text}</p>
            </div>
          ) : (
            <p className="empty-state">Todo revisado en este filtro.</p>
          )}

          <div className="review-actions">
            <button
              type="button"
              className="segment-tool"
              disabled={index <= 0 || !current}
              onClick={() => {
                go(index - 1)
              }}
            >
              Anterior
            </button>
            <button
              type="button"
              className="segment-tool"
              disabled={!current || index >= count - 1}
              onClick={() => {
                go(index + 1)
              }}
            >
              Siguiente
            </button>
            <button
              type="button"
              className="segment-tool review-done"
              disabled={!current}
              onClick={markReviewed}
            >
              Marcar como revisado
            </button>
          </div>
        </>
      )}
    </section>
  )
}
