import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ACCENTS,
  applyAppearance,
  resolveTheme,
  setAccent,
  setThemePreference,
  THEME_PREFERENCES,
} from './appearance'

afterEach(() => {
  vi.restoreAllMocks()
  window.localStorage.clear()
  setThemePreference('system')
  setAccent('blue')
})

describe('appearance', () => {
  it('ofrece los cuatro temas de Carbon más el automático', () => {
    expect(THEME_PREFERENCES).toEqual(['system', 'white', 'g10', 'g90', 'g100'])
  })

  it('en automático sigue al sistema: g100 oscuro, g10 claro', () => {
    expect(resolveTheme('system', false)).toBe('g100')
    expect(resolveTheme('system', true)).toBe('g10')
    expect(resolveTheme('g90', true)).toBe('g90')
    expect(resolveTheme('white', false)).toBe('white')
  })

  it('aplica la clase de zona y el acento en <html>', () => {
    applyAppearance('g90', 'teal')
    const root = document.documentElement
    expect(root.classList.contains('cds--g90')).toBe(true)
    expect(root.classList.contains('cds--g100')).toBe(false)
    expect(root.dataset.accent).toBe('teal')
    applyAppearance('white', 'blue')
    expect(root.classList.contains('cds--g90')).toBe(false)
    expect(root.classList.contains('cds--white')).toBe(true)
  })

  it('persiste tema y acento en localStorage', () => {
    setThemePreference('g10')
    setAccent('magenta')
    expect(window.localStorage.getItem('voz.theme')).toBe('g10')
    expect(window.localStorage.getItem('voz.accent')).toBe('magenta')
  })

  it('un localStorage bloqueado no lanza', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('bloqueado')
    })
    expect(() => {
      setThemePreference('g100')
      setAccent('red')
    }).not.toThrow()
  })

  it('hay ocho acentos y el azul es el de Carbon', () => {
    expect(ACCENTS).toHaveLength(8)
    expect(ACCENTS[0]).toBe('blue')
  })
})
