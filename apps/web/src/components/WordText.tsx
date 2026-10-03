import {
  memo,
  useSyncExternalStore,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from 'react'

import type { TranscriptSegment } from '../api/jobs'
import { findActiveWordIndex } from '../lib/activeWord'
import type { Playhead } from '../lib/playhead'
import { findMatches, type TextRange } from '../lib/segmentSearch'
import './WordText.scss'

interface WordTextProps {
  segment: TranscriptSegment
  // Posición del reproductor en ms. Pasarla por props re-renderiza todas las
  // filas en cada tick; en listas largas usa `playhead` (store externo).
  currentMs?: number | undefined
  playhead?: Playhead | undefined
  query?: string
  // Clic/Enter en una palabra: busca su inicio en el reproductor.
  onSeek?: ((ms: number) => void) | undefined
}

const NO_RANGES: readonly TextRange[] = []
const NOOP_SUBSCRIBE = () => () => undefined

/** Trozos de `text` (que ocupa [base, base+len) del texto unido) con <mark>. */
function withMarks(
  text: string,
  base: number,
  ranges: readonly TextRange[],
): ReactNode {
  if (ranges.length === 0) {
    return text
  }
  const parts: ReactNode[] = []
  let cursor = 0
  for (const range of ranges) {
    const start = Math.max(range.start - base, 0)
    const end = Math.min(range.end - base, text.length)
    if (end <= start || start < cursor) {
      continue
    }
    parts.push(text.slice(cursor, start))
    parts.push(
      <mark key={start} className="segment-match">
        {text.slice(start, end)}
      </mark>,
    )
    cursor = end
  }
  if (parts.length === 0) {
    return text
  }
  parts.push(text.slice(cursor))
  return parts
}

function wordIndexOf(target: EventTarget): number {
  const element =
    target instanceof Element ? target.closest<HTMLElement>('[data-word]') : null
  return element ? Number(element.dataset.word) : -1
}

/**
 * S7.06/S7.07: texto de un segmento como palabras clicables. Un único manejador
 * delegado por segmento (sin un botón por palabra: 10k segmentos son >100k
 * palabras) y tab-stop único con flechas (roving tabindex). Sin palabras (el
 * modelo no las dio, o el texto se editó) cae al texto plano del segmento.
 */
export const WordText = memo(function WordText({
  segment,
  currentMs,
  playhead,
  query = '',
  onSeek,
}: WordTextProps) {
  const { words } = segment
  const liveActive = useSyncExternalStore(
    playhead?.subscribe ?? NOOP_SUBSCRIBE,
    // La instantánea es el índice activo (un número): solo cambia de fila/palabra.
    () => {
      const time = playhead?.get()
      return time === undefined ||
        time < segment.start_ms ||
        time >= segment.end_ms
        ? -1
        : findActiveWordIndex(words, time)
    },
  )
  const active =
    currentMs === undefined
      ? liveActive
      : currentMs < segment.start_ms || currentMs >= segment.end_ms
        ? -1
        : findActiveWordIndex(words, currentMs)

  if (words.length === 0) {
    const ranges =
      query.trim() === '' ? NO_RANGES : findMatches(segment.text, query)
    return <p className="segment-text">{withMarks(segment.text, 0, ranges)}</p>
  }

  const joined = words.map((word) => word.text).join(' ')
  const ranges = query.trim() === '' ? NO_RANGES : findMatches(joined, query)

  function seekTo(index: number) {
    const word = words[index]
    if (word && onSeek) {
      onSeek(word.start_ms)
    }
  }

  function onClick(event: MouseEvent) {
    seekTo(wordIndexOf(event.target))
  }

  function onKeyDown(event: KeyboardEvent) {
    const index = wordIndexOf(event.target)
    if (index < 0) {
      return
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      seekTo(index)
    } else if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault()
      const current = event.target as HTMLElement
      const sibling =
        event.key === 'ArrowRight'
          ? current.nextElementSibling
          : current.previousElementSibling
      if (sibling instanceof HTMLElement) {
        sibling.focus()
      }
    }
  }

  const tabStop = Math.max(active, 0)
  // Posición de cada palabra en `joined` (para repartir los <mark>).
  const offsets: number[] = []
  let base = 0
  for (const word of words) {
    offsets.push(base)
    base += word.text.length + 1
  }
  const children = words.map((word, index) => {
    const offset = offsets[index] as number
    return (
      <span
        key={index}
        data-word={index}
        className={index === active ? 'word is-current' : 'word'}
        aria-current={index === active ? 'true' : undefined}
        {...(onSeek
          ? { role: 'button', tabIndex: index === tabStop ? 0 : -1 }
          : {})}
      >
        {withMarks(word.text, offset, ranges)}
        {index < words.length - 1 ? ' ' : null}
      </span>
    )
  })

  return (
    <p
      className="segment-text word-text"
      {...(onSeek ? { onClick, onKeyDown } : {})}
    >
      {children}
    </p>
  )
})
