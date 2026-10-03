import { describe, expect, it } from 'vitest'

import { blocksBySpeaker, neighborStart, rulerTicks } from './timeline'

describe('timeline', () => {
  it('une segmentos contiguos del mismo hablante y separa por pausas largas', () => {
    const map = blocksBySpeaker([
      { start_ms: 0, end_ms: 1000, speaker_id: 'a' },
      { start_ms: 1200, end_ms: 2000, speaker_id: 'a' },
      { start_ms: 2000, end_ms: 3000, speaker_id: 'b' },
      { start_ms: 9000, end_ms: 9500, speaker_id: 'a' },
      { start_ms: 9600, end_ms: 9700, speaker_id: null },
    ])
    expect(map.get('a')).toEqual([
      { start_ms: 0, end_ms: 2000 },
      { start_ms: 9000, end_ms: 9500 },
    ])
    expect(map.get('b')).toEqual([{ start_ms: 2000, end_ms: 3000 }])
    expect(map.get(null)).toEqual([{ start_ms: 9600, end_ms: 9700 }])
  })

  it('reduce 1312 segmentos a pocos bloques', () => {
    const segments = Array.from({ length: 1312 }, (_, i) => ({
      start_ms: i * 5000,
      end_ms: i * 5000 + 4500,
      speaker_id: i % 400 < 200 ? 'a' : 'b',
    }))
    const map = blocksBySpeaker(segments)
    const total = [...map.values()].reduce((sum, list) => sum + list.length, 0)
    expect(total).toBeLessThan(10)
  })

  it('elige marcas de regla legibles', () => {
    expect(rulerTicks(0)).toEqual([])
    expect(rulerTicks(60_000)).toEqual([0, 10_000, 20_000, 30_000, 40_000, 50_000, 60_000])
    const long = rulerTicks(6_420_000) // 1 h 47 min
    expect(long.length).toBeLessThanOrEqual(11)
    expect((long[1] ?? 0) % 60_000).toBe(0)
  })

  it('encuentra el bloque vecino', () => {
    const blocks = [
      { start_ms: 1000, end_ms: 2000 },
      { start_ms: 5000, end_ms: 6000 },
      { start_ms: 9000, end_ms: 9500 },
    ]
    expect(neighborStart(blocks, 1000, 1)).toBe(5000)
    expect(neighborStart(blocks, 9000, 1)).toBeNull()
    expect(neighborStart(blocks, 5200, -1)).toBe(1000)
    expect(neighborStart(blocks, 5000, -1)).toBe(1000)
    expect(neighborStart(blocks, 500, -1)).toBeNull()
  })
})
