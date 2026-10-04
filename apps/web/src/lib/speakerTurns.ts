/** Estadísticas y saltos por hablante sobre los segmentos cargados (funciones puras). */

export interface SpeakerSegment {
  id: string
  start_ms: number
  end_ms: number
  speaker_id: string | null
}

export interface Turn {
  start_ms: number
  end_ms: number
  /** Primer segmento de la intervención: es el que se resalta al saltar. */
  segment_id: string
}

/** Intervenciones de un hablante: tandas de segmentos consecutivos suyos. */
export function speakerTurns(
  segments: readonly SpeakerSegment[],
  speakerId: string,
): Turn[] {
  const turns: Turn[] = []
  let open = false
  for (const segment of segments) {
    if (segment.speaker_id !== speakerId) {
      open = false
      continue
    }
    const last = turns.at(-1)
    if (open && last !== undefined) {
      last.end_ms = Math.max(last.end_ms, segment.end_ms)
    } else {
      turns.push({ start_ms: segment.start_ms, end_ms: segment.end_ms, segment_id: segment.id })
      open = true
    }
  }
  return turns
}

/** Intervención siguiente (1) o anterior (-1) a `ms`, o `null`. */
export function neighborTurn(turns: readonly Turn[], ms: number, direction: 1 | -1): Turn | null {
  if (direction === 1) {
    return turns.find((turn) => turn.start_ms > ms + 50) ?? null
  }
  for (let i = turns.length - 1; i >= 0; i -= 1) {
    const turn = turns[i]
    if (turn !== undefined && turn.start_ms < ms - 1000) {
      return turn
    }
  }
  return null
}

/** Milisegundos de habla de un hablante según sus segmentos. */
export function talkMs(segments: readonly SpeakerSegment[], speakerId: string): number {
  let total = 0
  for (const segment of segments) {
    if (segment.speaker_id === speakerId) {
      total += Math.max(0, segment.end_ms - segment.start_ms)
    }
  }
  return total
}

export const SAMPLE_MAX_MS = 12_000

export interface Sample {
  start_ms: number
  end_ms: number
  segment_id: string
}

/**
 * Muestra para reconocer la voz: el segmento más largo del hablante (recortado a
 * `SAMPLE_MAX_MS`); a igualdad, el primero.
 */
export function pickSample(
  segments: readonly SpeakerSegment[],
  speakerId: string,
): Sample | null {
  let best: SpeakerSegment | null = null
  for (const segment of segments) {
    if (
      segment.speaker_id === speakerId &&
      (best === null ||
        Math.min(segment.end_ms - segment.start_ms, SAMPLE_MAX_MS) >
          Math.min(best.end_ms - best.start_ms, SAMPLE_MAX_MS))
    ) {
      best = segment
    }
  }
  return best === null
    ? null
    : {
        start_ms: best.start_ms,
        end_ms: Math.min(best.end_ms, best.start_ms + SAMPLE_MAX_MS),
        segment_id: best.id,
      }
}

/** Porcentaje entero de `part` sobre `whole` (0 si no hay total). */
export function percentOf(part: number, whole: number): number {
  return whole > 0 ? Math.round((part / whole) * 100) : 0
}
