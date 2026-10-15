import { afterEach, describe, expect, it, vi } from 'vitest'

import type { SynthesisModel, SynthesisOptions } from '../api/synthesis'
import {
  firstSentence,
  loadPreference,
  requestOf,
  resolveChoice,
  roundSpeed,
  sampleLanguage,
  SAMPLE_MAX_CHARS,
  savePreference,
} from './speakChoice'

const PIPER: SynthesisModel = {
  provider_id: 'sherpa-onnx',
  model_id: 'piper-es',
  display_name: 'Piper es',
  runtime_ready: true,
  languages: ['es'],
  voices: [
    { id: '0', name: 'Ald', languages: ['es'] },
    { id: '1', name: 'Claude', languages: ['es'] },
  ],
}

const KOKORO: SynthesisModel = {
  provider_id: 'sherpa-onnx',
  model_id: 'kokoro',
  display_name: 'Kokoro',
  runtime_ready: true,
  languages: ['en', 'es', 'fr'],
  voices: [
    { id: '1', name: 'Bella', languages: ['en'] },
    { id: '2', name: 'Dora', languages: ['es'] },
    { id: '3', name: 'Alex', languages: ['es'] },
    { id: '4', name: 'Siwis', languages: ['fr'] },
  ],
}

function options(...models: SynthesisModel[]): SynthesisOptions {
  return { providers: [], models, max_chars: 100, speed: { min: 0.5, max: 2 } }
}

afterEach(() => {
  vi.unstubAllGlobals()
  window.localStorage.clear()
})

describe('resolveChoice', () => {
  it('prefiere un modelo local aunque el primero disponible sea cloud', () => {
    const cloud = { ...KOKORO, provider_id: 'remote' }
    const available = options(cloud, PIPER)
    available.providers = [{ provider_id: 'remote', display_name: 'Remote', locality: 'cloud' }]
    expect(resolveChoice(available, {}, 'es').model).toBe(PIPER)
    expect(resolveChoice(available, { model: 'remote:kokoro' }, 'es').model).toBe(cloud)
  })

  it('sin preferencia toma el primer modelo listo y su primera voz', () => {
    const notReady = { ...PIPER, model_id: 'x', runtime_ready: false }
    const choice = resolveChoice(options(notReady, KOKORO), {}, 'en')

    expect(choice.model.model_id).toBe('kokoro')
    expect(choice.language).toBe('en')
    expect(choice.voice?.id).toBe('1')
    expect(choice.speed).toBe(1)
  })

  it('un modelo de un solo idioma no envía idioma', () => {
    const choice = resolveChoice(options(PIPER), {}, 'es')
    expect(choice.language).toBeNull()
    expect(choice.voices).toHaveLength(2)
  })

  it('el idioma de la interfaz es el inicial si el modelo lo tiene', () => {
    expect(resolveChoice(options(KOKORO), {}, 'es').language).toBe('es')
    expect(resolveChoice(options(KOKORO), {}, 'de').language).toBe('en')
  })

  it('las voces se filtran por idioma y una voz de otro idioma cae en la primera', () => {
    const choice = resolveChoice(
      options(KOKORO),
      { model: 'sherpa-onnx:kokoro', language: 'es', voice: '4' },
      'en',
    )
    expect(choice.voices.map((voice) => voice.name)).toEqual(['Dora', 'Alex'])
    expect(choice.voice?.name).toBe('Dora')
    expect(resolveChoice(options(KOKORO), { language: 'es', voice: '3' }, 'en').voice?.name).toBe('Alex')
  })

  it('si ninguna voz declara el idioma muestra todas en vez de ninguna', () => {
    const model = { ...KOKORO, languages: ['en', 'de'] }
    const choice = resolveChoice(options(model), { language: 'de' }, 'en')
    expect(choice.voices).toHaveLength(4)
  })

  it('un modelo que ya no está cae en otro y la velocidad queda dentro del rango', () => {
    const choice = resolveChoice(options(PIPER), { model: 'sherpa-onnx:borrado', speed: 9 }, 'es')
    expect(choice.model.model_id).toBe('piper-es')
    expect(choice.speed).toBe(2)
    expect(resolveChoice(options(PIPER), { speed: 0.1 }, 'es').speed).toBe(0.5)
  })

  it('sin voces el modelo se resuelve pero no hay voz ni petición', () => {
    const choice = resolveChoice(options({ ...PIPER, voices: [] }), {}, 'es')
    expect(choice.voice).toBeNull()
    expect(requestOf(choice)).toBeNull()
  })
})

describe('requestOf', () => {
  it('arma el cuerpo de POST sin el texto', () => {
    const choice = resolveChoice(options(KOKORO), { language: 'es', speed: 1.3 }, 'en')
    expect(requestOf(choice)).toEqual({
      provider_id: 'sherpa-onnx',
      model_id: 'kokoro',
      voice_id: '2',
      language: 'es',
      speed: 1.3,
    })
  })
})

describe('roundSpeed', () => {
  it('redondea al paso del control', () => {
    expect(roundSpeed(0.30000000000000004)).toBe(0.3)
    expect(roundSpeed(1.26)).toBe(1.3)
  })
})

describe('preferencia guardada', () => {
  it('va y vuelve por localStorage', () => {
    savePreference(resolveChoice(options(KOKORO), { language: 'fr', speed: 1.5 }, 'en'))
    expect(loadPreference()).toEqual({
      model: 'sherpa-onnx:kokoro',
      language: 'fr',
      speed: 1.5,
      voice: '4',
    })
  })

  it('ignora basura y campos de tipo erróneo', () => {
    window.localStorage.setItem('voz.speak.choice', '{no json')
    expect(loadPreference()).toEqual({})
    window.localStorage.setItem('voz.speak.choice', JSON.stringify({ model: 3, speed: 'rápido', voice: '2' }))
    expect(loadPreference()).toEqual({ voice: '2' })
  })

  it('si el almacenamiento lanza, ni lee ni escribe rompe', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new Error('bloqueado')
      },
      setItem: () => {
        throw new Error('bloqueado')
      },
    })
    expect(loadPreference()).toEqual({})
    expect(() => {
      savePreference(resolveChoice(options(PIPER), {}, 'es'))
    }).not.toThrow()
  })
})

describe('firstSentence', () => {
  it('toma la primera oración o línea', () => {
    expect(firstSentence('  Hola mundo. Segunda frase.')).toBe('Hola mundo.')
    expect(firstSentence('¿Qué tal? Bien')).toBe('¿Qué tal?')
    expect(firstSentence('Sin punto\nOtra línea')).toBe('Sin punto')
    expect(firstSentence('3.14 es pi. Sí')).toBe('3.14 es pi.')
  })

  it('vacío si no hay texto', () => {
    expect(firstSentence('   \n ')).toBe('')
  })

  it('corta en un espacio a 120 caracteres como máximo', () => {
    const long = 'palabra '.repeat(40)
    const sample = firstSentence(long)
    expect(Array.from(sample).length).toBeLessThanOrEqual(SAMPLE_MAX_CHARS)
    expect(sample.endsWith('palabra')).toBe(true)
    expect(Array.from(firstSentence('a'.repeat(500)))).toHaveLength(SAMPLE_MAX_CHARS)
  })
})

describe('sampleLanguage', () => {
  it('usa el idioma de la voz y, sin frase propia, inglés', () => {
    expect(sampleLanguage(resolveChoice(options(KOKORO), { language: 'fr' }, 'en'))).toBe('fr')
    const choice = resolveChoice(options({ ...PIPER, languages: ['de'], voices: [{ id: '0', name: 'x', languages: ['de'] }] }), {}, 'es')
    expect(sampleLanguage(choice)).toBe('en')
    expect(sampleLanguage(resolveChoice(options(PIPER), {}, 'en'))).toBe('es')
  })
})
