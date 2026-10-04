import { useId, useState } from 'react'
import { Button, Select, SelectItem, Tag } from '@carbon/react'
import { WarningAltFilled } from '@carbon/icons-react'

import type { TranscriptSegment } from '../api/jobs'
import { useI18n } from '../i18n/i18n'
import { formatStamp } from '../lib/formatTime'
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
  const { t, tn } = useI18n()
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
      title={t('review.title')}
      description={t('review.description')}
      className="voz-review"
      actions={
        count > 0 && current ? (
          <span role="status">
          <Button
            kind="tertiary"
            size="sm"
            title={t('review.goCount')}
            onClick={() => {
              onSelect(current)
            }}
          >
            {tn('review.count', count)}
          </Button>
          </span>
        ) : (
          <span role="status">
            <Tag type="green" size="md">
              {tn('review.count', count)}
            </Tag>
          </span>
        )
      }
    >
      {flagged.length === 0 ? (
        <p className="voz-field-note">{t('review.none')}</p>
      ) : (
        <>
          <Select
            id={filterId}
            labelText={t('review.kind')}
            value={filter}
            onChange={(event) => {
              setFilter(event.target.value)
              setPosition(0)
            }}
          >
            <SelectItem value={ALL} text={t('review.all')} />
            {kinds.map((kind) => (
              <SelectItem key={kind} value={kind} text={flagLabel(kind, t)} />
            ))}
          </Select>

          {current ? (
            <button
              type="button"
              className="voz-review__current"
              title={t('review.go')}
              onClick={() => {
                onSelect(current)
              }}
            >
              <span className="voz-review__flags">
                <WarningAltFilled size={16} aria-hidden="true" />
                {current.quality.flags.map((flag) => flagLabel(flag, t)).join(' · ')}
              </span>
              <span className="voz-review__time">
                {formatStamp(current.start_ms) + ' → ' + formatStamp(current.end_ms)}
              </span>
              <span className="voz-review__text">{current.text}</span>
            </button>
          ) : (
            <p className="voz-field-note">{t('review.allDone')}</p>
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
              {t('review.prev')}
            </Button>
            <Button
              kind="tertiary"
              size="md"
              disabled={!current || index >= count - 1}
              onClick={() => {
                go(index + 1)
              }}
            >
              {t('review.next')}
            </Button>
            <Button
              kind="primary"
              size="md"
              disabled={!current}
              onClick={markReviewed}
            >
              {t('review.markDone')}
            </Button>
          </div>
        </>
      )}
    </Panel>
  )
}
