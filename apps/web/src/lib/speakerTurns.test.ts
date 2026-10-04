import { describe, expect, it } from 'vitest'

import { neighborTurn, percentOf, pickSample, speakerTurns, talkMs } from './speakerTurns'

const seg = (id: string, start: number, end: number, speaker: string | null) => ({
  id,
  start_ms: start,
  end_ms: end,
  speaker_id: speaker,
})
const SEGMENTS = [
  seg('a', 0, 2000, 'x'),
  seg('b', 2000, 5000, 'x'),
  seg('c', 5000, 6000, 'y'),
  seg('d', 6000, 30_000, 'x'),
  seg('e', 30_000, 31_000, null),
]

describe('hablantes: intervenciones y muestras', () => {
  it('agrupa segmentos consecutivos del mismo hablante en una intervención', () => {
    expect(speakerTurns(SEGMENTS, 'x')).toEqual([
      { start_ms: 0, end_ms: 5000, segment_id: 'a' },
      { start_ms: 6000, end_ms: 30_000, segment_id: 'd' },
    ])
    expect(speakerTurns(SEGMENTS, 'nadie')).toEqual([])
  })

  it('salta a la intervención anterior y siguiente', () => {
    const turns = speakerTurns(SEGMENTS, 'x')
    expect(neighborTurn(turns, 0, 1)?.segment_id).toBe('d')
    expect(neighborTurn(turns, 7000, 1)).toBeNull()
    expect(neighborTurn(turns, 7000, -1)?.segment_id).toBe('a')
    expect(neighborTurn(turns, 500, -1)).toBeNull()
  })

  it('suma el tiempo de habla y calcula porcentajes', () => {
    expect(talkMs(SEGMENTS, 'x')).toBe(29_000)
    expect(talkMs(SEGMENTS, 'y')).toBe(1000)
    expect(percentOf(1000, 4000)).toBe(25)
    expect(percentOf(1, 0)).toBe(0)
  })

  it('la muestra es el segmento más largo recortado a 12 s', () => {
    expect(pickSample(SEGMENTS, 'x')).toEqual({ start_ms: 6000, end_ms: 18_000, segment_id: 'd' })
    expect(pickSample(SEGMENTS, 'y')?.segment_id).toBe('c')
    expect(pickSample(SEGMENTS, 'z')).toBeNull()
  })
})
