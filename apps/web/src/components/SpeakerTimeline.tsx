import {
  useMemo,
  useSyncExternalStore,
  type KeyboardEvent,
  type MouseEvent,
} from 'react'

import type { TranscriptSegment } from '../api/jobs'
import type { Speaker } from '../api/speakers'
import { useI18n } from '../i18n/i18n'
import { formatSeconds } from '../lib/formatTime'
import type { Playhead } from '../lib/playhead'
import {
  blocksBySpeaker,
  neighborStart,
  rulerTicks,
  type TimelineBlock,
} from '../lib/timeline'
import './SpeakerTimeline.scss'

interface SpeakerTimelineProps {
  segments: readonly TranscriptSegment[]
  speakers: readonly Speaker[]
  /** Duración total de la grabación; si falta, la del último segmento. */
  durationMs: number | null
  playhead: Playhead
  onSeek: (ms: number) => void
  /** Los hablantes se están calculando: se avisa en lugar de mostrar una sola fila. */
  speakersPending?: boolean
}

interface Lane {
  id: string | null
  name: string
  color: string | null
  blocks: TimelineBlock[]
}

function percent(ms: number, duration: number): string {
  return String(Math.min(100, Math.max(0, (ms / duration) * 100))) + '%'
}

function Cursor({ playhead, duration }: { playhead: Playhead; duration: number }) {
  const ms = useSyncExternalStore(playhead.subscribe, playhead.get)
  if (ms === undefined) {
    return null
  }
  return (
    <div
      className="voz-tl__cursor"
      aria-hidden="true"
      style={{ insetInlineStart: percent(ms, duration) }}
    />
  )
}

/**
 * Línea de tiempo de hablantes: una fila por hablante con bloques de color a lo largo
 * del audio, regla de tiempo y cursor sincronizado con la reproducción. Un clic salta.
 */
export function SpeakerTimeline({
  segments,
  speakers,
  durationMs,
  playhead,
  onSeek,
  speakersPending = false,
}: SpeakerTimelineProps) {
  const { t, tn } = useI18n()
  const duration =
    durationMs !== null && durationMs > 0
      ? durationMs
      : Math.max(0, ...segments.map((segment) => segment.end_ms))

  const lanes = useMemo<Lane[]>(() => {
    const blocks = blocksBySpeaker(segments)
    const result: Lane[] = []
    for (const speaker of speakers) {
      const list = blocks.get(speaker.id)
      if (list !== undefined && list.length > 0) {
        result.push({ id: speaker.id, name: speaker.name, color: speaker.color, blocks: list })
      }
    }
    const loose = blocks.get(null)
    if (loose !== undefined && loose.length > 0) {
      result.push({
        id: null,
        name: speakers.length > 0 ? t('tl.unassigned') : t('tl.voice'),
        color: null,
        blocks: loose,
      })
    }
    return result
  }, [segments, speakers, t])

  const ticks = useMemo(() => rulerTicks(duration), [duration])

  if (duration <= 0) {
    return <p className="voz-field-note">{t('tl.empty')}</p>
  }

  const seekAt = (event: MouseEvent<HTMLElement>, track: HTMLElement) => {
    const rect = track.getBoundingClientRect()
    if (rect.width <= 0) {
      return
    }
    const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width))
    onSeek(Math.round(ratio * duration))
  }

  const onTrackKey = (event: KeyboardEvent<HTMLElement>, blocks: TimelineBlock[]) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') {
      return
    }
    event.preventDefault()
    const target = neighborStart(blocks, playhead.get() ?? 0, event.key === 'ArrowRight' ? 1 : -1)
    if (target !== null) {
      onSeek(target)
    }
  }

  return (
    <div className="voz-tl" role="group" aria-label={t('tl.label')}>
      <div className="voz-tl__row voz-tl__row--ruler" aria-hidden="true">
        <span className="voz-tl__name" />
        <div className="voz-tl__ruler">
          {ticks.map((tick) => (
            <span key={tick} className="voz-tl__tick" style={{ insetInlineStart: percent(tick, duration) }}>
              {formatSeconds(tick / 1000)}
            </span>
          ))}
        </div>
      </div>
      <div className="voz-tl__lanes">
        {lanes.map((lane) => (
          <div key={lane.id ?? 'none'} className="voz-tl__row">
            <span className="voz-tl__name" title={lane.name}>
              <span
                className="voz-tl__chip"
                aria-hidden="true"
                style={lane.color ? { backgroundColor: lane.color } : undefined}
              />
              <span className="voz-tl__label">{lane.name}</span>
            </span>
            <div
              className="voz-tl__track"
              role="button"
              tabIndex={0}
              aria-label={t('tl.track', {
                name: lane.name,
                count: lane.blocks.length,
              })}
              onClick={(event) => {
                seekAt(event, event.currentTarget)
              }}
              onKeyDown={(event) => {
                onTrackKey(event, lane.blocks)
              }}
            >
              {lane.blocks.map((block) => (
                <span
                  key={block.start_ms}
                  className="voz-tl__block"
                  title={
                    lane.name +
                    ' · ' +
                    formatSeconds(block.start_ms / 1000) +
                    ' – ' +
                    formatSeconds(block.end_ms / 1000)
                  }
                  style={{
                    insetInlineStart: percent(block.start_ms, duration),
                    inlineSize: percent(block.end_ms - block.start_ms, duration),
                    ...(lane.color ? { backgroundColor: lane.color } : {}),
                  }}
                />
              ))}
            </div>
          </div>
        ))}
        <div className="voz-tl__overlay" aria-hidden="true">
          <Cursor playhead={playhead} duration={duration} />
        </div>
      </div>
      {speakersPending ? (
        <p className="voz-field-note" role="status">
          {t('tl.pending')}
        </p>
      ) : lanes.length > 1 ? (
        <p className="voz-field-note">{tn('tl.help', lanes.length)}</p>
      ) : null}
    </div>
  )
}
