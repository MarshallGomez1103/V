import {
  memo,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react'

import { getSegments, type TranscriptSegment } from '../api/jobs'
import { findActiveIndex } from '../lib/activeSegment'
import { scrollDelta } from '../lib/scrollDelta'
import {
  buildSearchIndex,
  type SearchIndex,
  type TextRange,
} from '../lib/segmentSearch'
import './SegmentList.css'

interface SegmentListProps {
  transcriptId: string | null
  // S5.10: si existe, cada marca de tiempo se vuelve un botón que busca el
  // instante en el reproductor del original.
  onSeek?: (startMs: number) => void
  // S5.11: posición del reproductor en ms; resalta y sigue el segmento activo.
  currentMs?: number | undefined
  // Sustituye el texto de la fila (p. ej. un editor). Debe tener identidad
  // estable (useCallback) o las filas memoizadas se re-renderizan todas.
  renderText?: (segment: TranscriptSegment, query: string) => ReactNode
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

const NO_RANGES: readonly TextRange[] = []
const SCROLL_KEYS = new Set([
  'ArrowUp',
  'ArrowDown',
  'PageUp',
  'PageDown',
  'Home',
  'End',
])

function highlight(
  text: string,
  ranges: readonly TextRange[],
  currentRange: number,
): ReactNode {
  if (ranges.length === 0) {
    return text
  }
  const parts: ReactNode[] = []
  let cursor = 0
  ranges.forEach((range, i) => {
    parts.push(text.slice(cursor, range.start))
    parts.push(
      <mark
        key={range.start}
        className={
          i === currentRange ? 'segment-match is-current' : 'segment-match'
        }
      >
        {text.slice(range.start, range.end)}
      </mark>,
    )
    cursor = range.end
  })
  parts.push(text.slice(cursor))
  return parts
}

interface SegmentRowProps {
  segment: TranscriptSegment
  index: number
  active: boolean
  ranges: readonly TextRange[]
  currentRange: number
  query: string
  onSeek: ((startMs: number) => void) | undefined
  renderText: SegmentListProps['renderText']
}

// S5.15: memoizada; con props primitivas/estables, un cambio de currentMs solo
// re-renderiza la fila que deja de estar activa y la que pasa a estarlo.
const SegmentRow = memo(function SegmentRow({
  segment,
  index,
  active,
  ranges,
  currentRange,
  query,
  onSeek,
  renderText,
}: SegmentRowProps) {
  const timestamp = (
    <time dateTime={durationAttribute(segment.start_ms)}>
      {formatTimestamp(segment.start_ms) +
        ' → ' +
        formatTimestamp(segment.end_ms)}
    </time>
  )
  return (
    <li
      className="segment-row"
      data-segment-index={index}
      aria-current={active ? 'true' : undefined}
    >
      {onSeek ? (
        <button
          type="button"
          className="segment-seek"
          onClick={() => {
            onSeek(segment.start_ms)
          }}
          aria-label={'Reproducir desde ' + formatTimestamp(segment.start_ms)}
        >
          {timestamp}
        </button>
      ) : (
        timestamp
      )}
      {renderText ? (
        <div className="segment-text">{renderText(segment, query)}</div>
      ) : (
        <p className="segment-text">
          {highlight(segment.text, ranges, currentRange)}
        </p>
      )}
    </li>
  )
})

function isEditable(target: EventTarget): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable ||
      target.matches('input, textarea, select, [contenteditable]'))
  )
}

function scrollRowIntoView(container: HTMLElement | null, index: number) {
  const row = container?.querySelector<HTMLElement>(
    '[data-segment-index="' + index + '"]',
  )
  if (!container || !row) {
    return
  }
  // Mueve solo el contenedor de la lista (scrollIntoView movería la página).
  const top = scrollDelta(
    container.getBoundingClientRect(),
    row.getBoundingClientRect(),
  )
  if (top !== 0) {
    container.scrollBy?.({ top, behavior: 'smooth' })
  }
}

interface TranscriptViewProps {
  segments: TranscriptSegment[]
  onSeek: SegmentListProps['onSeek']
  currentMs: number | undefined
  renderText: SegmentListProps['renderText']
}

function TranscriptView({
  segments,
  onSeek,
  currentMs,
  renderText,
}: TranscriptViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [query, setQuery] = useState('')
  const [matchIndex, setMatchIndex] = useState(0)
  const [follow, setFollow] = useState(true)

  const search: SearchIndex = useMemo(
    () => buildSearchIndex(segments, query),
    [segments, query],
  )
  const hitCount = search.hits.length
  const currentHit =
    hitCount > 0 ? (search.hits[matchIndex % hitCount] ?? null) : null
  const activeIndex =
    currentMs === undefined ? -1 : findActiveIndex(segments, currentMs)

  useEffect(() => {
    if (follow && activeIndex >= 0) {
      scrollRowIntoView(containerRef.current, activeIndex)
    }
  }, [follow, activeIndex])

  useEffect(() => {
    if (currentHit) {
      scrollRowIntoView(containerRef.current, currentHit.segment)
    }
  }, [currentHit])

  function step(delta: number) {
    if (hitCount === 0) {
      return
    }
    setFollow(false)
    setMatchIndex((index) => (index + delta + hitCount) % hitCount)
  }

  function pauseFollow() {
    setFollow(false)
  }

  function onSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter' && !event.nativeEvent.isComposing) {
      event.preventDefault()
      step(event.shiftKey ? -1 : 1)
    }
  }

  return (
    <>
      <div className="segment-tools" role="search">
        <input
          type="search"
          className="segment-search"
          aria-label="Buscar en la transcripción"
          placeholder="Buscar en el texto"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value)
            setMatchIndex(0)
            if (event.target.value.trim() !== '') {
              setFollow(false)
            }
          }}
          onKeyDown={onSearchKeyDown}
        />
        <span className="segment-search-count" role="status">
          {search.query === ''
            ? ''
            : hitCount === 0
              ? 'Sin coincidencias'
              : (matchIndex % hitCount) + 1 + ' de ' + hitCount}
        </span>
        <button
          type="button"
          className="segment-tool"
          aria-label="Coincidencia anterior"
          disabled={hitCount === 0}
          onClick={() => {
            step(-1)
          }}
        >
          ↑
        </button>
        <button
          type="button"
          className="segment-tool"
          aria-label="Coincidencia siguiente"
          disabled={hitCount === 0}
          onClick={() => {
            step(1)
          }}
        >
          ↓
        </button>
        {!follow && currentMs !== undefined ? (
          <button
            type="button"
            className="segment-tool segment-follow"
            onClick={() => {
              setFollow(true)
            }}
          >
            Seguir reproducción
          </button>
        ) : null}
      </div>

      {/* Cualquier gesto manual sobre la lista pausa el autoscroll. */}
      <div
        ref={containerRef}
        className="segments-scroll"
        role="region"
        aria-label="Lista de segmentos"
        tabIndex={0}
        onWheel={pauseFollow}
        onTouchStart={pauseFollow}
        onPointerDown={(event) => {
          // Solo el arrastre de la barra de scroll (el propio contenedor).
          if (event.target === event.currentTarget) {
            pauseFollow()
          }
        }}
        onKeyDown={(event) => {
          if (SCROLL_KEYS.has(event.key)) {
            pauseFollow()
          }
        }}
        onFocus={(event) => {
          if (isEditable(event.target)) {
            pauseFollow()
          }
        }}
      >
        {/* ponytail: content-visibility:auto evita layout/pintado de filas
            fuera de pantalla, pero los nodos DOM no se acotan. Si 10k
            segmentos se miden lentos, pasar a @tanstack/react-virtual. */}
        <ol className="segments">
          {segments.map((segment, index) => (
            <SegmentRow
              key={segment.id}
              segment={segment}
              index={index}
              active={index === activeIndex}
              ranges={search.ranges.get(index) ?? NO_RANGES}
              currentRange={
                currentHit?.segment === index ? currentHit.range : -1
              }
              query={search.query}
              onSeek={onSeek}
              renderText={renderText}
            />
          ))}
        </ol>
      </div>
    </>
  )
}

export function SegmentList({
  transcriptId,
  onSeek,
  currentMs,
  renderText,
}: SegmentListProps) {
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
        <TranscriptView
          key={transcriptId}
          segments={state.segments}
          onSeek={onSeek}
          currentMs={currentMs}
          renderText={renderText}
        />
      )}
    </section>
  )
}
