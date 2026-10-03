/**
 * Ventana de filas de altura variable para listas largas (1.300+ segmentos):
 * se renderizan solo las filas visibles más un margen, y el resto es relleno.
 * Funciones puras; el DOM y las mediciones viven en el componente.
 */

/** Posiciones acumuladas: `offsets[i]` es el borde superior de la fila `i` y el último, el total. */
export function buildOffsets(
  count: number,
  heightOf: (index: number) => number,
): number[] {
  const offsets = new Array<number>(count + 1)
  offsets[0] = 0
  for (let i = 0; i < count; i += 1) {
    offsets[i + 1] = (offsets[i] as number) + heightOf(i)
  }
  return offsets
}

/** Índice de la fila que contiene la posición `y` (acotado a [0, count-1]). */
export function indexAt(offsets: readonly number[], y: number): number {
  const count = offsets.length - 1
  if (count <= 0) {
    return 0
  }
  let low = 0
  let high = count - 1
  while (low < high) {
    const mid = (low + high + 1) >> 1
    if ((offsets[mid] as number) <= y) {
      low = mid
    } else {
      high = mid - 1
    }
  }
  return low
}

export interface RowRange {
  start: number
  /** Exclusivo. */
  end: number
}

/** Filas a pintar para una vista `[scrollTop, scrollTop + viewport]` con `overscan` filas de margen. */
export function visibleRange(
  offsets: readonly number[],
  scrollTop: number,
  viewport: number,
  overscan: number,
): RowRange {
  const count = offsets.length - 1
  if (count <= 0) {
    return { start: 0, end: 0 }
  }
  const first = indexAt(offsets, Math.max(0, scrollTop))
  const last = indexAt(offsets, Math.max(0, scrollTop + viewport))
  return {
    start: Math.max(0, first - overscan),
    end: Math.min(count, last + 1 + overscan),
  }
}

/**
 * Desplazamiento (scrollTop destino) para que la fila `index` quede visible, o `null`
 * si ya lo está. Una fila más alta que la vista muestra su inicio.
 */
export function scrollTarget(
  offsets: readonly number[],
  index: number,
  scrollTop: number,
  viewport: number,
): number | null {
  const top = offsets[index]
  const bottom = offsets[index + 1]
  if (top === undefined || bottom === undefined) {
    return null
  }
  if (top < scrollTop) {
    return top
  }
  if (bottom > scrollTop + viewport) {
    return Math.min(top, bottom - viewport)
  }
  return null
}
