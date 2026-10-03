import { describe, expect, it } from 'vitest'

import { formatDuration, formatSeconds, formatStamp } from './formatTime'
import { parseIso } from './time'

describe('parseIso', () => {
  it('lee fechas con zona y supone UTC si falta', () => {
    expect(parseIso('2026-10-01T10:00:00Z')).toBe(Date.UTC(2026, 9, 1, 10))
    expect(parseIso('2026-10-01T10:00:00+00:00')).toBe(Date.UTC(2026, 9, 1, 10))
    expect(parseIso('2026-10-01T05:00:00-05:00')).toBe(Date.UTC(2026, 9, 1, 10))
    expect(parseIso('2026-10-01T10:00:00')).toBe(Date.UTC(2026, 9, 1, 10))
  })

  it('devuelve null si no hay fecha válida', () => {
    expect(parseIso(null)).toBeNull()
    expect(parseIso(undefined)).toBeNull()
    expect(parseIso('')).toBeNull()
    expect(parseIso('mañana')).toBeNull()
  })
})

describe('formatTime', () => {
  it('formatea m:ss y h:mm:ss', () => {
    expect(formatSeconds(0)).toBe('0:00')
    expect(formatSeconds(75.9)).toBe('1:15')
    expect(formatSeconds(3725)).toBe('1:02:05')
    expect(formatSeconds(-3)).toBe('0:00')
    expect(formatDuration(6_464_000)).toBe('1:47:44')
    expect(formatDuration(125_000)).toBe('2:05')
  })

  it('la marca de tiempo lleva décimas', () => {
    expect(formatStamp(65_300)).toBe('01:05.3')
    expect(formatStamp(-5)).toBe('00:00.0')
  })
})
