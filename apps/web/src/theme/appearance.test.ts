import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ACCENTS,
  applyAppearance,
  applyDesign,
  DESIGN_SYSTEMS,
  isDarkTheme,
  resolveTheme,
  setAccent,
  setDesign,
  settleDesign,
  setThemePreference,
  THEME_PREFERENCES,
} from './appearance'

afterEach(() => {
  vi.restoreAllMocks()
  setThemePreference('system')
  setAccent('blue')
  setDesign('carbon')
  window.localStorage.clear()
  const root = document.documentElement
  root.removeAttribute('style')
  root.removeAttribute('data-design')
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

  it('ofrece Carbon y Material 3', () => {
    expect(DESIGN_SYSTEMS).toEqual(['carbon', 'm3'])
  })

  it('persiste el sistema de diseño en localStorage', () => {
    setDesign('m3')
    expect(window.localStorage.getItem('voz.design')).toBe('m3')
    setDesign('carbon')
    expect(window.localStorage.getItem('voz.design')).toBe('carbon')
  })

  it('un localStorage bloqueado no impide cambiar el diseño', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('bloqueado')
    })
    expect(() => {
      setDesign('m3')
    }).not.toThrow()
  })

  it('Gray 90 y Gray 100 son oscuros; White y Gray 10, claros', () => {
    expect(isDarkTheme('g100')).toBe(true)
    expect(isDarkTheme('g90')).toBe(true)
    expect(isDarkTheme('g10')).toBe(false)
    expect(isDarkTheme('white')).toBe(false)
  })

  it('con M3 publica los roles y marca data-design; con Carbon los quita', async () => {
    const root = document.documentElement
    await applyDesign('m3', 'teal', 'g10')
    expect(root.dataset.design).toBe('m3')
    expect(root.style.getPropertyValue('--md-sys-color-primary')).toMatch(/^#[0-9a-f]{6}$/)
    const light = root.style.getPropertyValue('--md-sys-color-surface')
    await applyDesign('m3', 'teal', 'g100')
    expect(root.style.getPropertyValue('--md-sys-color-surface')).not.toBe(light)

    await applyDesign('carbon', 'teal', 'g100')
    expect(root.dataset.design).toBe('carbon')
    expect(root.style.getPropertyValue('--md-sys-color-primary')).toBe('')
    expect(root.style.getPropertyValue('--voz-m3-success')).toBe('')
  })

  it('una aplicación más nueva descarta a la anterior', async () => {
    const root = document.documentElement
    const first = applyDesign('m3', 'blue', 'g100')
    await applyDesign('carbon', 'blue', 'g100')
    await first
    expect(root.dataset.design).toBe('carbon')
    expect(root.style.getPropertyValue('--md-sys-color-primary')).toBe('')
  })

  it('settleDesign aplica el diseño guardado', async () => {
    setDesign('m3')
    await settleDesign()
    expect(document.documentElement.dataset.design).toBe('m3')
  })

  it('al arrancar usa Carbon salvo que esté guardado Material 3; lo inválido cae a Carbon', async () => {
    window.localStorage.setItem('voz.design', 'nope')
    vi.resetModules()
    let fresh = await import('./appearance')
    await fresh.settleDesign()
    expect(document.documentElement.dataset.design).toBe('carbon')

    window.localStorage.setItem('voz.design', 'm3')
    vi.resetModules()
    fresh = await import('./appearance')
    await fresh.settleDesign()
    expect(document.documentElement.dataset.design).toBe('m3')
  })
})
