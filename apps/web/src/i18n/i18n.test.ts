import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  detectLang,
  getLang,
  localeOf,
  pluralKey,
  setLang,
  translate,
  translateCode,
  translatePlural,
} from './i18n'
import { MESSAGES, type MessageKey } from './messages'

afterEach(() => {
  vi.restoreAllMocks()
  window.localStorage.clear()
  setLang('es')
})

function placeholders(text: string): string[] {
  return [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1] ?? '').sort()
}

describe('catálogo de mensajes', () => {
  const entries = Object.entries(MESSAGES) as [MessageKey, readonly [string, string]][]

  it('todo mensaje existe en español e inglés', () => {
    expect(entries.length).toBeGreaterThan(400)
    for (const [key, [es, en]] of entries) {
      expect(es.trim(), key + ' (es)').not.toBe('')
      expect(en.trim(), key + ' (en)').not.toBe('')
    }
  })

  it('ambas versiones usan las mismas variables', () => {
    for (const [key, [es, en]] of entries) {
      expect(placeholders(en), key).toEqual(placeholders(es))
    }
  })

  it('las variantes plurales vienen por pares', () => {
    const keys = new Set(entries.map(([key]) => key as string))
    for (const key of keys) {
      if (key.endsWith('_one')) {
        expect(keys.has(key.slice(0, -4) + '_other'), key).toBe(true)
      }
    }
  })

  it('el inglés no se quedó con el español sin traducir (salvo nombres propios)', () => {
    const same = entries.filter(([, [es, en]]) => es === en && /[a-záéíóúñ]{5,}/i.test(es))
    // Solo marcas y términos que se escriben igual en ambos idiomas.
    expect(same.length).toBeLessThan(25)
  })

  it('la cadena de la referencia visual no aparece en ningún texto', () => {
    const forbidden = ['eleven' + 'labs', 'buzz']
    for (const [key, [es, en]] of entries) {
      for (const word of forbidden) {
        expect((es + ' ' + en).toLowerCase(), key).not.toContain(word)
      }
    }
  })
})

describe('idioma', () => {
  it('por defecto sigue a navigator.language: español solo si empieza por es', () => {
    window.localStorage.clear()
    const language = vi.spyOn(window.navigator, 'language', 'get')
    language.mockReturnValue('es-CO')
    expect(detectLang()).toBe('es')
    language.mockReturnValue('es')
    expect(detectLang()).toBe('es')
    language.mockReturnValue('en-US')
    expect(detectLang()).toBe('en')
    language.mockReturnValue('pt-BR')
    expect(detectLang()).toBe('en')
  })

  it('lo guardado manda sobre el del navegador', () => {
    vi.spyOn(window.navigator, 'language', 'get').mockReturnValue('en-US')
    window.localStorage.setItem('voz.lang', 'es')
    expect(detectLang()).toBe('es')
    window.localStorage.setItem('voz.lang', 'xx')
    expect(detectLang()).toBe('en')
  })

  it('setLang persiste, actualiza <html lang> y cambia las traducciones', () => {
    setLang('en')
    expect(getLang()).toBe('en')
    expect(window.localStorage.getItem('voz.lang')).toBe('en')
    expect(document.documentElement.lang).toBe('en')
    expect(translate('nav.modelos')).toBe('Models')
    setLang('es')
    expect(translate('nav.modelos')).toBe('Modelos')
  })

  it('un localStorage bloqueado no impide cambiar de idioma ni detectarlo', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('bloqueado')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('bloqueado')
    })
    expect(() => detectLang()).not.toThrow()
    setLang('en')
    expect(getLang()).toBe('en')
  })

  it('sustituye variables y deja intactas las que faltan', () => {
    expect(translate('import.fileReady', { size: '4 B' })).toBe('Archivo listo · 4 B')
    expect(translate('import.fileReady')).toBe('Archivo listo · {size}')
  })

  it('elige singular o plural', () => {
    expect(translatePlural('seg.count', 1)).toBe('1 segmento')
    expect(translatePlural('seg.count', 5)).toBe('5 segmentos')
    expect(pluralKey('seg.count', 0)).toBe('seg.count_other')
    setLang('en')
    expect(translatePlural('seg.count', 1)).toBe('1 segment')
  })

  it('translateCode usa el mensaje del código o el genérico con el código', () => {
    expect(translateCode('err.job.', 'job_terminal', 'err.job.generic')).toMatch(/ya terminó/)
    expect(translateCode('err.job.', 'rara', 'err.job.generic')).toBe(
      'No se pudo completar la operación (código rara).',
    )
  })

  it('localeOf da una etiqueta BCP 47', () => {
    expect(localeOf('es')).toBe('es-CO')
    expect(localeOf('en')).toBe('en-US')
  })
})
