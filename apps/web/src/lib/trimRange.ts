// Tramo de la grabación que se transcribe: validación y contrato, sin DOM.

/** Tramo `[startMs, endMs)` en milisegundos de la grabación original. */
export interface TrimRange {
  startMs: number
  endMs: number
}

export type TrimError = 'order' | 'too_short' | 'out_of_range'

/** Mismos límites que el servidor: al menos 1 s y paso de 100 ms en los controles. */
export const MIN_TRIM_MS = 1000
export const TRIM_STEP_MS = 100

/** `null` si el tramo es válido para una grabación de `durationMs`. */
export function validateTrim(startMs: number, endMs: number, durationMs: number): TrimError | null {
  if (startMs >= endMs) {
    return 'order'
  }
  if (endMs - startMs < MIN_TRIM_MS) {
    return 'too_short'
  }
  if (startMs < 0 || endMs > durationMs) {
    return 'out_of_range'
  }
  return null
}

/** Valor del campo `clip` de `POST /api/jobs`; `null` = grabación completa. */
export function clipOf(
  range: TrimRange | null,
  durationMs: number,
): { start_ms: number; end_ms: number } | null {
  if (range === null || (range.startMs <= 0 && range.endMs >= durationMs)) {
    return null
  }
  return { start_ms: range.startMs, end_ms: range.endMs }
}

/** `mm:ss`, o `h:mm:ss` desde una hora. */
export function formatTrimTime(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const pad = (n: number) => String(n).padStart(2, '0')
  return hours > 0
    ? String(hours) + ':' + pad(minutes) + ':' + pad(total % 60)
    : pad(minutes) + ':' + pad(total % 60)
}

/** Tiempos ya formateados del tramo, el total y lo que queda sin transcribir. */
export function trimSummary(startMs: number, endMs: number, totalMs: number) {
  return {
    start: formatTrimTime(startMs),
    end: formatTrimTime(endMs),
    total: formatTrimTime(totalMs),
    omitted: formatTrimTime(totalMs - (endMs - startMs)),
  }
}
