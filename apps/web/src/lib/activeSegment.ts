export interface TimedSegment {
  start_ms: number
  end_ms: number
}

/**
 * S5.11: índice del segmento que suena en `ms`, o -1 si ninguno.
 *
 * Supone `segments` ordenados por `start_ms` (contrato del backend). Búsqueda
 * binaria del último segmento con `start_ms <= ms`; ese es el activo solo si
 * `ms < end_ms` (fin exclusivo, así en segmentos contiguos gana el siguiente).
 * Decisión: en un hueco entre segmentos, o antes del primero, NO hay activo
 * (el resaltado significa "esto se está diciendo ahora"; el autoscroll solo se
 * dispara al entrar en un segmento, así que un hueco no lo mueve). Con
 * segmentos solapados (habla simultánea) prevalece el que empezó más tarde.
 */
export function findActiveIndex(
  segments: readonly TimedSegment[],
  ms: number,
): number {
  let low = 0
  let high = segments.length - 1
  let candidate = -1
  while (low <= high) {
    const mid = (low + high) >> 1
    const segment = segments[mid] as TimedSegment
    if (segment.start_ms <= ms) {
      candidate = mid
      low = mid + 1
    } else {
      high = mid - 1
    }
  }
  if (candidate < 0) {
    return -1
  }
  return ms < (segments[candidate] as TimedSegment).end_ms ? candidate : -1
}
