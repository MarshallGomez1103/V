import { useId, useState } from 'react'
import { Button, Select, SelectItem, Tag } from '@carbon/react'
import { WarningAltFilled } from '@carbon/icons-react'

import type { TranscriptSegment } from '../api/jobs'
import { flagLabel, flaggedSegments } from '../lib/qualityFlags'
import { Panel } from './Panel'
import './ReviewQueue.scss'

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
  const filterId = useId()

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
    <Panel
      titleId="review-title"
      title="Revisión"
      className="voz-review"
      actions={
        <span role="status">
          <Tag type={count > 0 ? 'warm-gray' : 'green'} size="md">
            {count === 1
              ? '1 segmento por revisar'
              : count + ' segmentos por revisar'}
          </Tag>
        </span>
      }
    >
      {flagged.length === 0 ? (
        <p className="voz-field-note">Ningún segmento necesita revisión.</p>
      ) : (
        <>
          <Select
            id={filterId}
            labelText="Tipo"
            value={filter}
            onChange={(event) => {
              setFilter(event.target.value)
              setPosition(0)
            }}
          >
            <SelectItem value={ALL} text="Todos" />
            {kinds.map((kind) => (
              <SelectItem key={kind} value={kind} text={flagLabel(kind)} />
            ))}
          </Select>

          {current ? (
            <div className="voz-review__current">
              <p className="voz-review__flags">
                <WarningAltFilled size={16} aria-hidden="true" />
                {current.quality.flags.map(flagLabel).join(' · ')}
              </p>
              <p className="voz-review__text">{current.text}</p>
            </div>
          ) : (
            <p className="voz-field-note">Todo revisado en este filtro.</p>
          )}

          <div className="voz-review__actions">
            <Button
              kind="tertiary"
              size="md"
              disabled={index <= 0 || !current}
              onClick={() => {
                go(index - 1)
              }}
            >
              Anterior
            </Button>
            <Button
              kind="tertiary"
              size="md"
              disabled={!current || index >= count - 1}
              onClick={() => {
                go(index + 1)
              }}
            >
              Siguiente
            </Button>
            <Button
              kind="primary"
              size="md"
              disabled={!current}
              onClick={markReviewed}
            >
              Marcar como revisado
            </Button>
          </div>
        </>
      )}
    </Panel>
  )
}
