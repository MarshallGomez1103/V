export interface TimedWord {
  start_ms: number
  end_ms: number
}

/**
 * S7.06: índice de la palabra que suena en `ms`, o -1 si ninguna.
 *
 * Supone `words` ordenadas por `start_ms` (contrato del backend). Búsqueda
 * binaria de la última palabra con `start_ms <= ms`. A diferencia de los
 * segmentos, una pausa ENTRE palabras mantiene resaltada la última dicha (el
 * resaltado no parpadea al respirar); solo tras el fin de la última palabra, o
 * antes de la primera, no hay activa.
 */
export function findActiveWordIndex(
  words: readonly TimedWord[],
  ms: number,
): number {
  let low = 0
  let high = words.length - 1
  let candidate = -1
  while (low <= high) {
    const mid = (low + high) >> 1
    if ((words[mid] as TimedWord).start_ms <= ms) {
      candidate = mid
      low = mid + 1
    } else {
      high = mid - 1
    }
  }
  if (candidate === words.length - 1 && candidate >= 0) {
    return ms < (words[candidate] as TimedWord).end_ms ? candidate : -1
  }
  return candidate
}
