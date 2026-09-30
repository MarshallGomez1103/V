import { describe, expect, it } from 'vitest'

import { findActiveIndex } from './activeSegment'

const segments = [
  { start_ms: 1000, end_ms: 2000 },
  { start_ms: 2000, end_ms: 3000 },
  { start_ms: 4000, end_ms: 5000 },
]

describe('findActiveIndex', () => {
  it('devuelve -1 con lista vacía', () => {
    expect(findActiveIndex([], 10)).toBe(-1)
  })

  it('devuelve -1 antes del primer segmento', () => {
    expect(findActiveIndex(segments, 999)).toBe(-1)
  })

  it('incluye el inicio y excluye el fin', () => {
    expect(findActiveIndex(segments, 1000)).toBe(0)
    expect(findActiveIndex(segments, 1999)).toBe(0)
  })

  it('en segmentos contiguos gana el siguiente en la frontera', () => {
    expect(findActiveIndex(segments, 2000)).toBe(1)
  })

  it('devuelve -1 en un hueco entre segmentos', () => {
    expect(findActiveIndex(segments, 3000)).toBe(-1)
    expect(findActiveIndex(segments, 3999)).toBe(-1)
  })

  it('devuelve -1 tras el último segmento', () => {
    expect(findActiveIndex(segments, 5000)).toBe(-1)
    expect(findActiveIndex(segments, 99_999)).toBe(-1)
  })

  it('encuentra el segmento correcto en una lista larga', () => {
    const many = Array.from({ length: 10_000 }, (_, i) => ({
      start_ms: i * 1000,
      end_ms: i * 1000 + 900,
    }))
    expect(findActiveIndex(many, 7_654_500)).toBe(7654)
    expect(findActiveIndex(many, 9_999_950)).toBe(-1)
    expect(findActiveIndex(many, 9_999_000)).toBe(9999)
  })
})
