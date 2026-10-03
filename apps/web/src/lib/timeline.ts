/** Geometría pura de la línea de tiempo de hablantes (sin DOM). */

export interface TimedSpeakerSegment {
  start_ms: number
  end_ms: number
  speaker_id: string | null
}

export interface TimelineBlock {
  start_ms: number
  end_ms: number
}

/** Pausa máxima entre dos segmentos del mismo hablante para pintarlos como un solo bloque. */
export const MERGE_GAP_MS = 1500

/**
 * Bloques por hablante (`null` = sin hablante). Une segmentos contiguos del mismo
 * hablante: miles de segmentos quedan en unos cientos de bloques sin perder cobertura.
 * Supone los segmentos ordenados por inicio (contrato del backend).
 */
export function blocksBySpeaker(
  segments: readonly TimedSpeakerSegment[],
  gapMs: number = MERGE_GAP_MS,
): Map<string | null, TimelineBlock[]> {
  const result = new Map<string | null, TimelineBlock[]>()
  for (const segment of segments) {
    const list = result.get(segment.speaker_id) ?? []
    const last = list.at(-1)
    if (last !== undefined && segment.start_ms - last.end_ms <= gapMs) {
      last.end_ms = Math.max(last.end_ms, segment.end_ms)
    } else {
      list.push({ start_ms: segment.start_ms, end_ms: segment.end_ms })
    }
    result.set(segment.speaker_id, list)
  }
  return result
}

const TICK_STEPS_S = [
  1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 14400,
] as const

/** Marcas de la regla (ms): el paso más pequeño que deja como mucho `maxTicks` marcas. */
export function rulerTicks(durationMs: number, maxTicks = 10): number[] {
  if (!(durationMs > 0)) {
    return []
  }
  const step =
    TICK_STEPS_S.find((candidate) => (durationMs / 1000) / candidate <= maxTicks) ??
    TICK_STEPS_S[TICK_STEPS_S.length - 1]
  const stepMs = (step ?? 1) * 1000
  const ticks: number[] = []
  for (let at = 0; at <= durationMs; at += stepMs) {
    ticks.push(at)
  }
  return ticks
}

/** Inicio del bloque siguiente (dirección 1) o anterior (-1) a `ms`, o `null`. */
export function neighborStart(
  blocks: readonly TimelineBlock[],
  ms: number,
  direction: 1 | -1,
): number | null {
  if (direction === 1) {
    return blocks.find((block) => block.start_ms > ms + 50)?.start_ms ?? null
  }
  for (let i = blocks.length - 1; i >= 0; i -= 1) {
    const block = blocks[i]
    if (block !== undefined && block.start_ms < ms - 1000) {
      return block.start_ms
    }
  }
  return null
}
