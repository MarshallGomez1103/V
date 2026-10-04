import { describe, expect, it } from 'vitest'

import { ACCENT_SWATCH, ACCENTS } from './appearance'
import { applyM3Roles, m3Roles } from './m3'

/** Luminancia relativa WCAG 2.x de un color `#rrggbb`. */
function luminance(hex: string): number {
  const channels = [1, 3, 5].map((start) => {
    const value = parseInt(hex.slice(start, start + 2), 16) / 255
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * (channels[0] ?? 0) + 0.7152 * (channels[1] ?? 0) + 0.0722 * (channels[2] ?? 0)
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return ((hi ?? 0) + 0.05) / ((lo ?? 0) + 0.05)
}

const PAIRS: [string, string][] = [
  ['on-surface', 'surface'],
  ['on-surface-variant', 'surface'],
  ['on-surface', 'surface-container-highest'],
  ['on-primary', 'primary'],
  ['on-secondary-container', 'secondary-container'],
  ['on-primary-container', 'primary-container'],
  ['on-tertiary-container', 'tertiary-container'],
  ['on-error', 'error'],
  ['on-error-container', 'error-container'],
]

describe('roles de color M3', () => {
  for (const accent of ACCENTS) {
    for (const dark of [false, true]) {
      const label = accent + (dark ? ' oscuro' : ' claro')
      const roles = m3Roles(ACCENT_SWATCH[accent], accent === 'neutral', dark)
      const role = (name: string) => roles['--md-sys-color-' + name] ?? ''

      it(`${label}: texto normal de los pares principales con contraste >= 4,5:1`, () => {
        for (const [on, base] of PAIRS) {
          expect(contrast(role(on), role(base)), `${on} sobre ${base}`).toBeGreaterThanOrEqual(4.5)
        }
      })

      it(`${label}: bordes y acento con contraste >= 3:1 sobre la superficie`, () => {
        expect(contrast(role('outline'), role('surface'))).toBeGreaterThanOrEqual(3)
        expect(contrast(role('primary'), role('surface'))).toBeGreaterThanOrEqual(3)
      })

      it(`${label}: éxito y aviso a medida con su texto legible`, () => {
        for (const name of ['success', 'warning']) {
          const base = roles['--voz-m3-' + name + '-container'] ?? ''
          const on = roles['--voz-m3-on-' + name + '-container'] ?? ''
          expect(contrast(on, base), name).toBeGreaterThanOrEqual(4.5)
          expect(roles['--voz-m3-' + name]).toMatch(/^#[0-9a-f]{6}$/)
        }
      })
    }
  }

  it('el claro y el oscuro dan superficies distintas, claras y oscuras', () => {
    const light = m3Roles('#0f62fe', false, false)['--md-sys-color-surface'] ?? ''
    const dark = m3Roles('#0f62fe', false, true)['--md-sys-color-surface'] ?? ''
    expect(luminance(light)).toBeGreaterThan(0.8)
    expect(luminance(dark)).toBeLessThan(0.05)
  })

  it('el acento rojo sigue siendo rojo (Vibrant, no el apagado de TonalSpot)', () => {
    const primary = m3Roles(ACCENT_SWATCH.red, false, false)['--md-sys-color-primary'] ?? '#000000'
    const [red, green, blue] = [1, 3, 5].map((i) => parseInt(primary.slice(i, i + 2), 16))
    expect(red).toBeGreaterThan(2 * (green ?? 0))
    expect(red).toBeGreaterThan(2 * (blue ?? 0))
  })

  it('el acento neutral no tiñe de color la interfaz', () => {
    const primary = m3Roles(ACCENT_SWATCH.neutral, true, false)['--md-sys-color-primary'] ?? '#000000'
    const channels = [1, 3, 5].map((i) => parseInt(primary.slice(i, i + 2), 16))
    expect(Math.max(...channels) - Math.min(...channels)).toBeLessThan(12)
  })

  it('applyM3Roles escribe las variables en el elemento', () => {
    const element = document.createElement('div')
    applyM3Roles(element, '#0f62fe', false, false)
    expect(element.style.getPropertyValue('--md-sys-color-primary')).toMatch(/^#[0-9a-f]{6}$/)
    expect(element.style.getPropertyValue('--voz-m3-warning')).toMatch(/^#[0-9a-f]{6}$/)
  })
})
