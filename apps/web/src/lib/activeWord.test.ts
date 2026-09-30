import { describe, expect, it } from 'vitest'

import { findActiveWordIndex } from './activeWord'

const words = [
  { start_ms: 1000, end_ms: 1400 },
  { start_ms: 1400, end_ms: 1800 },
  { start_ms: 2500, end_ms: 3000 },
]

describe('findActiveWordIndex', () => {
  it('devuelve -1 con lista vacía', () => {
    expect(findActiveWordIndex([], 10)).toBe(-1)
  })

  it('devuelve -1 antes de la primera palabra', () => {
    expect(findActiveWordIndex(words, 999)).toBe(-1)
  })

  it('incluye el inicio y, en palabras contiguas, gana la siguiente', () => {
    expect(findActiveWordIndex(words, 1000)).toBe(0)
    expect(findActiveWordIndex(words, 1399)).toBe(0)
    expect(findActiveWordIndex(words, 1400)).toBe(1)
  })

  it('mantiene la última palabra dicha durante una pausa interna', () => {
    expect(findActiveWordIndex(words, 1800)).toBe(1)
    expect(findActiveWordIndex(words, 2499)).toBe(1)
    expect(findActiveWordIndex(words, 2500)).toBe(2)
  })

  it('devuelve -1 tras el fin de la última palabra', () => {
    expect(findActiveWordIndex(words, 2999)).toBe(2)
    expect(findActiveWordIndex(words, 3000)).toBe(-1)
  })

  it('encuentra la palabra correcta en una lista larga', () => {
    const many = Array.from({ length: 100_000 }, (_, i) => ({
      start_ms: i * 100,
      end_ms: i * 100 + 90,
    }))
    expect(findActiveWordIndex(many, 5_432_150)).toBe(54321)
    expect(findActiveWordIndex(many, 9_999_990)).toBe(-1)
  })
})
