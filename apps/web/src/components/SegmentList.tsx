import {
  memo,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react'
import { Button, DismissibleTag, IconButton, Search } from '@carbon/react'
import { ArrowDown, ArrowUp, PlayFilledAlt, WarningAltFilled } from '@carbon/icons-react'

import { getSegments, type TranscriptSegment } from '../api/jobs'
import type { Speaker } from '../api/speakers'
import { useI18n } from '../i18n/i18n'
import { findActiveIndex } from '../lib/activeSegment'
import { formatStamp } from '../lib/formatTime'
import { flagLabel } from '../lib/qualityFlags'
import {
  buildSearchIndex,
  type SearchIndex,
  type TextRange,
} from '../lib/segmentSearch'
import { buildOffsets, scrollTarget, visibleRange } from '../lib/virtualRows'
import { Busy } from './Busy'
import { Notice } from './Notice'
import { Panel } from './Panel'
import './SegmentList.scss'

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
  // Control de hablante de la fila (columna izquierda); misma regla de identidad.
  renderSpeaker?: ((segment: TranscriptSegment) => ReactNode) | undefined
  // Hablantes conocidos: dan el color de la fila y el nombre si no hay `renderSpeaker`.
  speakers?: readonly Speaker[]
  // Cambiarlo recarga los segmentos (p. ej. tras reasignar speakers) sin
  // perder búsqueda ni scroll: se conserva la lista vieja hasta que llega la nueva.
  reloadKey?: number
  // S13.06: entrega los segmentos cargados (p. ej. a la cola de revisión).
  // Se llama cada vez que llega una lista nueva; no necesita ser estable.
  onSegmentsLoaded?: (segments: TranscriptSegment[]) => void
  // Controles a la derecha del título del panel (modo, guardado, exportar).
  headerActions?: ReactNode
  // Aviso encima de la lista (p. ej. «hablantes en proceso»).
  notice?: ReactNode
  // Muestra solo los segmentos de este hablante (`null` = todos).
  speakerFilter?: string | null
  // Cada cambio de `nonce` desplaza la lista a ese segmento y lo resalta un momento.
  focus?: { segmentId: string; nonce: number } | null
  // Quita el filtro de hablante desde la etiqueta de la lista.
  onClearFilter?: () => void
}

type Outcome =
  | { phase: 'error'; message: string | null }
  | { phase: 'ready'; segments: TranscriptSegment[] }

interface Loaded {
  transcriptId: string
  outcome: Outcome
}

function durationAttribute(ms: number): string {
  return 'PT' + (Math.max(0, ms) / 1000).toFixed(1) + 'S'
}

const NO_RANGES: readonly TextRange[] = []
const noop = () => undefined
const SCROLL_KEYS = new Set([
  'ArrowUp',
  'ArrowDown',
  'PageUp',
  'PageDown',
  'Home',
  'End',
])
// Altura supuesta de una fila sin medir y vista supuesta cuando el navegador no mide.
const ROW_ESTIMATE = 96
const FALLBACK_VIEWPORT = 640
const OVERSCAN = 6

interface Measure {
  heights: ReadonlyMap<number, number>
  estimate: number
}

const NO_MEASURES: Measure = { heights: new Map(), estimate: ROW_ESTIMATE }

/** Incorpora alturas medidas; devuelve el mismo objeto si nada cambió (sin re-render). */
function withMeasures(previous: Measure, seen: readonly (readonly [number, number])[]): Measure {
  let next: Map<number, number> | null = null
  for (const [index, height] of seen) {
    if (Math.abs((previous.heights.get(index) ?? 0) - height) > 1) {
      next ??= new Map(previous.heights)
      next.set(index, height)
    }
  }
  if (next === null) {
    return previous
  }
  let sum = 0
  next.forEach((value) => {
    sum += value
  })
  return { heights: next, estimate: Math.round(sum / next.size) }
}

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
  total: number
  active: boolean
  ranges: readonly TextRange[]
  currentRange: number
  query: string
  color: string | undefined
  speakerName: string | undefined
  // Paridad del `nonce` de foco si esta fila es el segmento resaltado (reinicia la animación).
  focusPhase: 'a' | 'b' | undefined
  onSeek: ((startMs: number) => void) | undefined
  renderText: SegmentListProps['renderText']
  renderSpeaker: SegmentListProps['renderSpeaker']
}

// S5.15: memoizada; con props primitivas/estables, un cambio de currentMs solo
// re-renderiza la fila que deja de estar activa y la que pasa a estarlo.
const SegmentRow = memo(function SegmentRow({
  segment,
  index,
  total,
  active,
  ranges,
  currentRange,
  query,
  color,
  speakerName,
  focusPhase,
  onSeek,
  renderText,
  renderSpeaker,
}: SegmentRowProps) {
  const { t } = useI18n()
  const timestamp = (
    <time dateTime={durationAttribute(segment.start_ms)}>
      {formatStamp(segment.start_ms) + ' → ' + formatStamp(segment.end_ms)}
    </time>
  )
  const flags = segment.quality.flags
  const flagged = flags.length > 0
  return (
    <li
      className={
        (flagged ? 'segment-row has-flags' : 'segment-row') +
        (focusPhase ? ' is-focused-' + focusPhase : '')
      }
      data-segment-index={index}
      aria-posinset={index + 1}
      aria-setsize={total}
      aria-current={active ? 'true' : undefined}
      style={color ? ({ '--voz-speaker': color } as React.CSSProperties) : undefined}
    >
      <div className="segment-meta">
        {renderSpeaker ? (
          renderSpeaker(segment)
        ) : speakerName ? (
          <span className="segment-speaker">
            <span className="segment-speaker__chip" aria-hidden="true" />
            {speakerName}
          </span>
        ) : null}
        {onSeek ? (
          <button
            type="button"
            className="segment-seek"
            onClick={() => {
              onSeek(segment.start_ms)
            }}
            aria-label={t('seg.playFrom', { time: formatStamp(segment.start_ms) })}
          >
            {timestamp}
          </button>
        ) : (
          timestamp
        )}
      </div>
      {flagged ? (
        <span
          className="segment-flag"
          role="img"
          aria-label={t('seg.flagged', {
            flags: flags.map((flag) => flagLabel(flag, t)).join(', '),
          })}
          title={flags.map((flag) => flagLabel(flag, t)).join(', ')}
        >
          <WarningAltFilled size={16} aria-hidden="true" />
        </span>
      ) : null}
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

interface TranscriptViewProps {
  segments: TranscriptSegment[]
  speakerFilter: string | null
  focus: SegmentListProps['focus']
  onClearFilter: () => void
  speakers: readonly Speaker[]
  onSeek: SegmentListProps['onSeek']
  currentMs: number | undefined
  renderText: SegmentListProps['renderText']
  renderSpeaker: SegmentListProps['renderSpeaker']
}

function TranscriptView({
  segments: allSegments,
  speakerFilter,
  focus,
  onClearFilter,
  speakers,
  onSeek,
  currentMs,
  renderText,
  renderSpeaker,
}: TranscriptViewProps) {
  const { t } = useI18n()
  const containerRef = useRef<HTMLDivElement>(null)
  const [query, setQuery] = useState('')
  const [matchIndex, setMatchIndex] = useState(0)
  const [follow, setFollow] = useState(true)
  const [scrollTop, setScrollTop] = useState(0)
  const [viewport, setViewport] = useState(0)
  // Alturas medidas por fila y la estimación (media) para las que aún no se midieron.
  const [measure, setMeasure] = useState<Measure>(NO_MEASURES)

  const segments = useMemo(
    () =>
      speakerFilter === null
        ? allSegments
        : allSegments.filter((segment) => segment.speaker_id === speakerFilter),
    [allSegments, speakerFilter],
  )
  const search: SearchIndex = useMemo(
    () => buildSearchIndex(segments, query),
    [segments, query],
  )
  const hitCount = search.hits.length
  const currentHit =
    hitCount > 0 ? (search.hits[matchIndex % hitCount] ?? null) : null
  const activeIndex =
    currentMs === undefined ? -1 : findActiveIndex(segments, currentMs)
  const speakerById = useMemo(
    () => new Map(speakers.map((speaker) => [speaker.id, speaker])),
    [speakers],
  )

  const offsets = useMemo(
    () => buildOffsets(segments.length, (i) => measure.heights.get(i) ?? measure.estimate),
    [segments.length, measure],
  )
  const view = viewport > 0 ? viewport : FALLBACK_VIEWPORT
  const range = visibleRange(offsets, scrollTop, view, OVERSCAN)
  const total = offsets[segments.length] ?? 0

  // Mide la vista y las filas pintadas; las alturas reales sustituyen a la estimación.
  useEffect(() => {
    const container = containerRef.current
    if (!container || typeof ResizeObserver === 'undefined') {
      return
    }
    let frame = 0
    const refresh = () => {
      frame = 0
      setViewport(container.clientHeight)
      const seen: [number, number][] = []
      container.querySelectorAll<HTMLElement>('[data-segment-index]').forEach((row) => {
        if (row.offsetHeight > 0) {
          seen.push([Number(row.dataset.segmentIndex), row.offsetHeight])
        }
      })
      setMeasure((previous) => withMeasures(previous, seen))
    }
    const schedule = () => {
      if (frame === 0) {
        frame = requestAnimationFrame(refresh)
      }
    }
    const observer = new ResizeObserver(schedule)
    observer.observe(container)
    container.querySelectorAll('[data-segment-index]').forEach((row) => {
      observer.observe(row)
    })
    schedule()
    return () => {
      observer.disconnect()
      if (frame !== 0) {
        cancelAnimationFrame(frame)
      }
    }
  }, [range.start, range.end])

  function scrollToIndex(index: number) {
    const container = containerRef.current
    if (!container) {
      return
    }
    const top = container.scrollTop
    const height = container.clientHeight > 0 ? container.clientHeight : FALLBACK_VIEWPORT
    const target = scrollTarget(offsets, index, top, height)
    if (target === null) {
      return
    }
    // Deja la fila a un cuarto de la vista para leer lo que viene después.
    const destination = Math.max(0, (offsets[index] ?? 0) - height / 4)
    const far = Math.abs(destination - top) > height * 3
    container.scrollTo?.({ top: destination, behavior: far ? 'auto' : 'smooth' })
  }

  useEffect(() => {
    if (follow && activeIndex >= 0) {
      scrollToIndex(activeIndex)
    }
    // scrollToIndex lee posiciones vigentes; solo importa cuándo cambia el activo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [follow, activeIndex])

  // V0-06: tras un salto lejano el destino se calculó con alturas estimadas; al
  // medirse las filas pintadas cambian las posiciones y el activo puede quedar fuera
  // de la vista. Se realinea (scrollTarget es null si ya se ve, así que converge).
  useEffect(() => {
    if (follow && activeIndex >= 0) {
      scrollToIndex(activeIndex)
    }
    // Solo importa cuándo cambian las posiciones medidas.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offsets])

  const scrollRef = useRef(scrollToIndex)
  useEffect(() => {
    scrollRef.current = scrollToIndex
  })
  const focusNonce = focus?.nonce
  const focusId = focus?.segmentId
  useEffect(() => {
    if (focusNonce === undefined || focusId === undefined) {
      return
    }
    const index = segments.findIndex((segment) => segment.id === focusId)
    if (index < 0) {
      return
    }
    scrollRef.current(index)
    // Se vuelve a seguir la reproducción (el salto la reanuda); las filas lejanas se
    // miden al pintarse, así que la posición se corrige una vez medidas.
    const follow = setTimeout(() => {
      setFollow(true)
    }, 0)
    const timer = setTimeout(() => {
      scrollRef.current(index)
    }, 250)
    return () => {
      clearTimeout(follow)
      clearTimeout(timer)
    }
    // Solo importa cuándo se pide un foco nuevo, no cada cambio de la lista.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusNonce, focusId])

  useEffect(() => {
    if (currentHit) {
      scrollToIndex(currentHit.segment)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  const rows: ReactNode[] = []
  for (let index = range.start; index < range.end; index += 1) {
    const segment = segments[index]
    if (!segment) {
      break
    }
    const speaker = segment.speaker_id === null ? undefined : speakerById.get(segment.speaker_id)
    rows.push(
      <SegmentRow
        key={segment.id}
        segment={segment}
        index={index}
        total={segments.length}
        active={index === activeIndex}
        ranges={search.ranges.get(index) ?? NO_RANGES}
        currentRange={currentHit?.segment === index ? currentHit.range : -1}
        query={search.query}
        color={speaker?.color}
        speakerName={speaker?.name}
        focusPhase={
          focus !== null && focus !== undefined && focus.segmentId === segment.id
            ? focus.nonce % 2 === 0
              ? 'a'
              : 'b'
            : undefined
        }
        onSeek={onSeek}
        renderText={renderText}
        renderSpeaker={renderSpeaker}
      />,
    )
  }

  return (
    <>
      <div className="segment-tools">
        <Search
          size="md"
          className="segment-search"
          labelText={t('seg.search.label')}
          closeButtonLabelText={t('seg.search.clear')}
          placeholder={t('seg.search.placeholder')}
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
              ? t('seg.search.none')
              : t('seg.search.count', { current: (matchIndex % hitCount) + 1, total: hitCount })}
        </span>
        <IconButton
          kind="ghost"
          size="md"
          label={t('seg.search.prev')}
          disabled={hitCount === 0}
          onClick={() => {
            step(-1)
          }}
        >
          <ArrowUp />
        </IconButton>
        <IconButton
          kind="ghost"
          size="md"
          label={t('seg.search.next')}
          disabled={hitCount === 0}
          onClick={() => {
            step(1)
          }}
        >
          <ArrowDown />
        </IconButton>
        {speakerFilter !== null ? (
          <DismissibleTag
            type="gray"
            size="md"
            text={t('spk.filtering', {
              name: speakerById.get(speakerFilter)?.name ?? t('tl.unassigned'),
            })}
            dismissTooltipLabel={t('spk.filtering.clear')}
            title={t('spk.filtering.clear')}
            onClose={onClearFilter}
          />
        ) : null}
        {!follow && currentMs !== undefined ? (
          <Button
            kind="tertiary"
            size="md"
            renderIcon={PlayFilledAlt}
            onClick={() => {
              setFollow(true)
            }}
          >
            {t('seg.follow')}
          </Button>
        ) : null}
      </div>

      {/* Cualquier gesto manual sobre la lista pausa el autoscroll. */}
      <div
        ref={containerRef}
        className="segments-scroll"
        role="region"
        aria-label={t('seg.list')}
        tabIndex={0}
        onScroll={(event) => {
          setScrollTop(event.currentTarget.scrollTop)
        }}
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
        {segments.length === 0 ? (
          <p className="voz-field-note segment-filter-empty" role="status">
            {t('spk.filtering.none')}
          </p>
        ) : null}
        {/* Solo se pintan las filas visibles (más un margen): una transcripción de
            horas con miles de segmentos sigue abriéndose al instante. */}
        <ol
          className="segments"
          style={{
            paddingBlockStart: offsets[range.start] ?? 0,
            paddingBlockEnd: Math.max(0, total - (offsets[range.end] ?? total)),
          }}
        >
          {rows}
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
  renderSpeaker,
  speakers = [],
  reloadKey = 0,
  onSegmentsLoaded,
  headerActions,
  notice,
  speakerFilter = null,
  focus = null,
  onClearFilter = noop,
}: SegmentListProps) {
  const { t, tn } = useI18n()
  // El estado se asocia al id cargado; si no coincide con la prop, seguimos
  // cargando. Así el efecto nunca llama a setState de forma sincrónica.
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [attempt, setAttempt] = useState(0)
  const onLoadedRef = useRef(onSegmentsLoaded)
  useEffect(() => {
    onLoadedRef.current = onSegmentsLoaded
  })

  useEffect(() => {
    if (transcriptId === null) {
      return
    }

    const controller = new AbortController()

    void getSegments(transcriptId, controller.signal)
      .then((segments) => {
        setLoaded({ transcriptId, outcome: { phase: 'ready', segments } })
        onLoadedRef.current?.(segments)
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }
        setLoaded({
          transcriptId,
          outcome: {
            phase: 'error',
            message: error instanceof Error ? error.message : null,
          },
        })
      })

    return () => {
      controller.abort()
    }
  }, [transcriptId, reloadKey, attempt])

  if (transcriptId === null) {
    return null
  }

  const state: Outcome | { phase: 'loading' } =
    loaded !== null && loaded.transcriptId === transcriptId
      ? loaded.outcome
      : { phase: 'loading' }

  return (
    <Panel
      titleId="segments-title"
      title={t('seg.title')}
      description={
        state.phase === 'ready' && state.segments.length > 0
          ? tn('seg.count', state.segments.length)
          : undefined
      }
      actions={headerActions}
      className="voz-segments"
    >
      {notice}
      {state.phase === 'loading' ? (
        <div role="status">
          <Busy description={t('seg.loading')} />
        </div>
      ) : state.phase === 'error' ? (
        <Notice
          kind="error"
          title={t('seg.error.title')}
          subtitle={state.message ?? t('seg.error.generic')}
          action={{
            label: t('common.retry'),
            onClick: () => {
              setLoaded(null)
              setAttempt((current) => current + 1)
            },
          }}
        />
      ) : state.segments.length === 0 ? (
        <p className="voz-field-note">{t('seg.empty')}</p>
      ) : (
        <TranscriptView
          key={transcriptId}
          segments={state.segments}
          speakerFilter={speakerFilter}
          focus={focus}
          onClearFilter={onClearFilter}
          speakers={speakers}
          onSeek={onSeek}
          currentMs={currentMs}
          renderText={renderText}
          renderSpeaker={renderSpeaker}
        />
      )}
    </Panel>
  )
}
