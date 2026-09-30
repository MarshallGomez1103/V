import { describe, expect, it } from 'vitest'

import { scrollDelta } from './scrollDelta'

const container = { top: 100, bottom: 400 }

describe('scrollDelta', () => {
  it('no mueve si la fila ya es visible', () => {
    expect(scrollDelta(container, { top: 150, bottom: 200 })).toBe(0)
    expect(scrollDelta(container, { top: 100, bottom: 400 })).toBe(0)
  })

  it('sube lo justo si la fila está por encima', () => {
    expect(scrollDelta(container, { top: 60, bottom: 110 })).toBe(-40)
  })

  it('baja lo justo si la fila está por debajo', () => {
    expect(scrollDelta(container, { top: 380, bottom: 450 })).toBe(50)
  })

  it('con una fila más alta que el contenedor prioriza su inicio', () => {
    expect(scrollDelta(container, { top: 300, bottom: 900 })).toBe(200)
    expect(scrollDelta(container, { top: 50, bottom: 900 })).toBe(-50)
  })
})
