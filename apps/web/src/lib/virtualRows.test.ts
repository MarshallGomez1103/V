import { describe, expect, it } from 'vitest'

import { buildOffsets, indexAt, scrollTarget, visibleRange } from './virtualRows'

describe('virtualRows', () => {
  const offsets = buildOffsets(5, (i) => 10 * (i + 1)) // 0,10,30,60,100,150

  it('acumula alturas variables', () => {
    expect(offsets).toEqual([0, 10, 30, 60, 100, 150])
    expect(buildOffsets(0, () => 1)).toEqual([0])
  })

  it('encuentra la fila de una posición, acotada a los extremos', () => {
    expect(indexAt(offsets, 0)).toBe(0)
    expect(indexAt(offsets, 9)).toBe(0)
    expect(indexAt(offsets, 10)).toBe(1)
    expect(indexAt(offsets, 59)).toBe(2)
    expect(indexAt(offsets, 149)).toBe(4)
    expect(indexAt(offsets, 9999)).toBe(4)
    expect(indexAt([0], 5)).toBe(0)
  })

  it('calcula la ventana visible con margen', () => {
    expect(visibleRange(offsets, 35, 30, 0)).toEqual({ start: 2, end: 4 })
    expect(visibleRange(offsets, 35, 30, 1)).toEqual({ start: 1, end: 5 })
    expect(visibleRange(offsets, 0, 5, 2)).toEqual({ start: 0, end: 3 })
    expect(visibleRange([0], 0, 100, 3)).toEqual({ start: 0, end: 0 })
  })

  it('da el scroll mínimo para ver una fila, o null si ya se ve', () => {
    // vista [0, 40]
    expect(scrollTarget(offsets, 1, 0, 40)).toBeNull()
    // fila 3 = [60,100] debajo de la vista: baja lo justo para ver su final
    expect(scrollTarget(offsets, 3, 0, 40)).toBe(60)
    // fila por encima de la vista
    expect(scrollTarget(offsets, 1, 50, 40)).toBe(10)
    // fila más alta que la vista: muestra su inicio
    expect(scrollTarget(offsets, 4, 0, 20)).toBe(100)
    expect(scrollTarget(offsets, 9, 0, 20)).toBeNull()
  })
})
