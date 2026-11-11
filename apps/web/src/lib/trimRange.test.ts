import { describe, expect, it } from 'vitest'

import { clipOf, formatTrimTime, trimSummary, validateTrim } from './trimRange'

describe('validateTrim', () => {
  it('rechaza un tramo vacío o invertido', () => {
    expect(validateTrim(5000, 5000, 60000)).toBe('order')
    expect(validateTrim(8000, 5000, 60000)).toBe('order')
  })

  it('rechaza un tramo de menos de un segundo', () => {
    expect(validateTrim(0, 900, 60000)).toBe('too_short')
    expect(validateTrim(0, 999, 60000)).toBe('too_short')
  })

  it('rechaza un tramo fuera de la grabación', () => {
    expect(validateTrim(0, 61000, 60000)).toBe('out_of_range')
    expect(validateTrim(-100, 5000, 60000)).toBe('out_of_range')
  })

  it('devuelve null con un tramo válido, también en los bordes', () => {
    expect(validateTrim(0, 1000, 60000)).toBeNull()
    expect(validateTrim(10000, 60000, 60000)).toBeNull()
  })
})

describe('clipOf', () => {
  it('envía null si el tramo cubre toda la grabación o no hay tramo', () => {
    expect(clipOf(null, 60000)).toBeNull()
    expect(clipOf({ startMs: 0, endMs: 60000 }, 60000)).toBeNull()
  })

  it('envía el tramo en el contrato HTTP', () => {
    expect(clipOf({ startMs: 10000, endMs: 20000 }, 60000)).toEqual({ start_ms: 10000, end_ms: 20000 })
  })
})

describe('formatTrimTime y trimSummary', () => {
  it('formatea mm:ss con ceros y h:mm:ss desde una hora', () => {
    expect(formatTrimTime(10_000)).toBe('00:10')
    expect(formatTrimTime(720_000)).toBe('12:00')
    expect(formatTrimTime(3_725_000)).toBe('1:02:05')
  })

  it('resume tramo, total y lo omitido', () => {
    expect(trimSummary(10_000, 310_000, 720_000)).toEqual({
      start: '00:10',
      end: '05:10',
      total: '12:00',
      omitted: '07:00',
    })
  })
})
