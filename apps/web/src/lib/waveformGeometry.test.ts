import { describe, expect, it } from 'vitest'

import {
  clampScrollLeft,
  clampZoom,
  columnPeaks,
  contentWidth,
  formatClock,
  isVisibleX,
  msToX,
  scrollLeftForZoom,
  scrollLeftToReveal,
  seekTarget,
  xToMs,
  zoomIn,
  zoomOut,
} from './waveformGeometry'

describe('zoom', () => {
  it('acota a enteros entre 1 y 32 y tolera valores inválidos', () => {
    expect(clampZoom(0)).toBe(1)
    expect(clampZoom(-4)).toBe(1)
    expect(clampZoom(2.6)).toBe(3)
    expect(clampZoom(99)).toBe(32)
    expect(clampZoom(Number.NaN)).toBe(1)
    expect(clampZoom(Number.POSITIVE_INFINITY)).toBe(1)
  })

  it('acercar duplica y alejar divide sin salir del rango', () => {
    expect(zoomIn(1)).toBe(2)
    expect(zoomIn(24)).toBe(32)
    expect(zoomIn(32)).toBe(32)
    expect(zoomOut(8)).toBe(4)
    expect(zoomOut(1)).toBe(1)
  })

  it('el ancho del contenido escala con el zoom', () => {
    expect(contentWidth(600, 1)).toBe(600)
    expect(contentWidth(600, 8)).toBe(4800)
    expect(contentWidth(0, 4)).toBe(1)
  })
})

describe('x <-> ms', () => {
  it('convierte y acota en ambos sentidos', () => {
    expect(msToX(5000, 10_000, 800)).toBe(400)
    expect(msToX(-5, 10_000, 800)).toBe(0)
    expect(msToX(20_000, 10_000, 800)).toBe(800)
    expect(msToX(100, 0, 800)).toBe(0)
    expect(xToMs(400, 10_000, 800)).toBe(5000)
    expect(xToMs(-30, 10_000, 800)).toBe(0)
    expect(xToMs(9999, 10_000, 800)).toBe(10_000)
    expect(xToMs(10, 10_000, 0)).toBe(0)
  })

  it('ida y vuelta es estable a la precisión del píxel', () => {
    const ms = xToMs(msToX(3333, 60_000, 4800), 60_000, 4800)
    expect(Math.abs(ms - 3333)).toBeLessThanOrEqual(13)
  })
})

describe('scroll', () => {
  it('acota scrollLeft al contenido', () => {
    expect(clampScrollLeft(-10, 600, 2400)).toBe(0)
    expect(clampScrollLeft(5000, 600, 2400)).toBe(1800)
    expect(clampScrollLeft(50, 600, 300)).toBe(0)
  })

  it('detecta si una x está en la vista', () => {
    expect(isVisibleX(100, 100, 600)).toBe(true)
    expect(isVisibleX(700, 100, 600)).toBe(true)
    expect(isVisibleX(701, 100, 600)).toBe(false)
    expect(isVisibleX(99, 100, 600)).toBe(false)
  })

  it('revela centrando solo cuando está fuera', () => {
    expect(scrollLeftToReveal(500, 400, 300, 3000)).toBe(400)
    expect(scrollLeftToReveal(1000, 0, 300, 3000)).toBe(850)
    expect(scrollLeftToReveal(2990, 0, 300, 3000)).toBe(2700)
  })

  it('el zoom conserva la posición del playhead en la vista', () => {
    // 1x -> 4x, playhead en la mitad (x=300 de 600), sin scroll previo.
    const scroll = scrollLeftForZoom({
      playheadMs: 5000,
      durationMs: 10_000,
      viewportWidth: 600,
      oldZoom: 1,
      newZoom: 4,
      scrollLeft: 0,
    })
    expect(scroll).toBe(1200 - 300)
  })

  it('el zoom centra el playhead si estaba fuera de la vista', () => {
    const scroll = scrollLeftForZoom({
      playheadMs: 9000,
      durationMs: 10_000,
      viewportWidth: 600,
      oldZoom: 4,
      newZoom: 8,
      scrollLeft: 0,
    })
    const playheadX = msToX(9000, 10_000, 4800)
    expect(isVisibleX(playheadX, scroll, 600)).toBe(true)
    expect(scroll).toBe(Math.min(playheadX - 300, 4800 - 600))
  })

  it('al alejar hasta 1x el scroll vuelve a 0', () => {
    expect(
      scrollLeftForZoom({
        playheadMs: 5000,
        durationMs: 10_000,
        viewportWidth: 600,
        oldZoom: 4,
        newZoom: 1,
        scrollLeft: 900,
      }),
    ).toBe(0)
  })
})

describe('seekTarget', () => {
  it('salta 5 s y se acota a la duración', () => {
    expect(seekTarget(10_000, 1, 60_000)).toBe(15_000)
    expect(seekTarget(10_000, -1, 60_000)).toBe(5000)
    expect(seekTarget(2000, -1, 60_000)).toBe(0)
    expect(seekTarget(58_000, 1, 60_000)).toBe(60_000)
    expect(seekTarget(1000, 1, 60_000, 250)).toBe(1250)
  })
})

describe('columnPeaks', () => {
  const peaks: [number, number][] = [
    [-0.1, 0.1],
    [-0.5, 0.2],
    [-0.2, 0.9],
    [-0.3, 0.3],
  ]

  it('agrega varios buckets en una columna cuando hay menos píxeles', () => {
    expect(columnPeaks(peaks, 0, 2, 2)).toEqual([
      [-0.5, 0.2],
      [-0.3, 0.9],
    ])
  })

  it('repite el bucket más cercano cuando hay más píxeles que buckets', () => {
    const columns = columnPeaks(peaks, 0, 8, 8)
    expect(columns).toHaveLength(8)
    expect(columns[0]).toEqual([-0.1, 0.1])
    expect(columns[1]).toEqual([-0.1, 0.1])
    expect(columns[7]).toEqual([-0.3, 0.3])
  })

  it('respeta scrollLeft y no pasa del final', () => {
    const columns = columnPeaks(peaks, 6, 8, 8)
    expect(columns).toHaveLength(2)
    expect(columns[0]).toEqual([-0.3, 0.3])
  })

  it('sin peaks o sin ancho no devuelve columnas', () => {
    expect(columnPeaks([], 0, 10, 10)).toEqual([])
    expect(columnPeaks(peaks, 0, 10, 0)).toEqual([])
  })
})

describe('formatClock', () => {
  it('formatea m:ss', () => {
    expect(formatClock(0)).toBe('0:00')
    expect(formatClock(65_900)).toBe('1:05')
    expect(formatClock(-5)).toBe('0:00')
    expect(formatClock(3_600_000)).toBe('60:00')
  })
})
