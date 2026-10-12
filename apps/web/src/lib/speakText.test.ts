import { describe, expect, it } from 'vitest'

import { speakTextStatus } from './speakText'

describe('speakTextStatus', () => {
  it('el texto vacío o en blanco no se puede generar', () => {
    for (const text of ['', '   \n\t ']) {
      expect(speakTextStatus(text, 100)).toMatchObject({
        chars: 0,
        words: 0,
        level: 'empty',
        canGenerate: false,
      })
    }
  })

  it('cuenta caracteres sobre el texto recortado y palabras separadas por cualquier blanco', () => {
    const status = speakTextStatus('  Hola   mundo\ncómo estás  ', 100)
    expect(status.chars).toBe('Hola   mundo\ncómo estás'.length)
    expect(status.words).toBe(4)
    expect(status).toMatchObject({ level: 'ok', canGenerate: true })
  })

  it('cuenta puntos de código, no unidades UTF-16', () => {
    expect(speakTextStatus('😀😀', 10).chars).toBe(2)
  })

  it('avisa al llegar al 90 % y sigue permitiendo generar', () => {
    expect(speakTextStatus('a'.repeat(89), 100).level).toBe('ok')
    const near = speakTextStatus('a'.repeat(90), 100)
    expect(near).toMatchObject({ level: 'near', left: 10, over: 0, canGenerate: true })
    expect(speakTextStatus('a'.repeat(100), 100)).toMatchObject({ level: 'near', left: 0, canGenerate: true })
  })

  it('bloquea al pasarse e indica cuántos caracteres sobran', () => {
    expect(speakTextStatus('a'.repeat(105), 100)).toMatchObject({
      level: 'over',
      over: 5,
      left: 0,
      canGenerate: false,
    })
  })

  it('los espacios al borde no cuentan para el límite', () => {
    expect(speakTextStatus(' ' + 'a'.repeat(100) + ' ', 100).canGenerate).toBe(true)
  })
})
