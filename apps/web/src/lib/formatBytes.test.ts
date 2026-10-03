import { describe, expect, it } from 'vitest'

import { formatBytes } from './formatBytes'

describe('formatBytes', () => {
  it.each([
    [0, '0 B'],
    [512, '512 B'],
    [77_003_619, '77 MB'],
    [1_620_000_000, '1,6 GB'],
    [3_000_000_000, '3 GB'],
    [120_000_000_000, '120 GB'],
    [-5, '0 B'],
  ])('%d -> %s', (input, expected) => {
    expect(formatBytes(input)).toBe(expected)
  })
})

describe('formatBytes en inglés', () => {
  it('usa punto decimal', async () => {
    const { setLang } = await import('../i18n/i18n')
    setLang('en')
    expect(formatBytes(1_620_000_000)).toBe('1.6 GB')
    setLang('es')
  })
})
