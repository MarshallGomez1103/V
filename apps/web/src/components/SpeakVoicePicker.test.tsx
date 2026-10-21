import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SynthesisOptions } from '../api/synthesis'
import { setLang } from '../i18n/i18n'
import { resolveChoice, type SpeakPreference } from '../lib/speakChoice'
import { SpeakVoicePicker } from './SpeakVoicePicker'

afterEach(() => { cleanup(); setLang('es') })

function picker(capabilities?: string[], locality = 'local') {
  const options: SynthesisOptions = {
    providers: [{ provider_id: 'engine', display_name: 'Engine', locality }],
    models: [{ provider_id: 'engine', model_id: 'voice', display_name: 'Voice', runtime_ready: true, languages: ['es'], voices: [{ id: '0', name: 'Voice A', languages: ['es'] }], ...(capabilities === undefined ? {} : { capabilities }) }],
    max_chars: 20000, speed: { min: 0.5, max: 2 },
  }
  render(<SpeakVoicePicker id="picker" options={options} choice={resolveChoice(options, {}, 'es')} onChange={vi.fn()} />)
}

describe('SpeakVoicePicker devices', () => {
  it.each([
    ['es', ['cpu'], 'Compatible con CPU'],
    ['es', ['gpu', 'cpu'], 'Compatible con CPU y GPU (una a la vez)'],
    ['en', ['cpu'], 'Supports CPU'],
    ['en', ['gpu'], 'Supports GPU'],
  ] as const)('muestra únicamente capacidades declaradas (%s, %s)', (lang, capabilities, label) => {
    setLang(lang)
    picker([...capabilities])
    expect(screen.getByText(label)).toBeDefined()
    expect(screen.queryByText(/Automático:|Automatic:/)).toBeNull()
  })

  it.each([undefined, [], ['future_device']])('no inventa dispositivo con capacidades desconocidas (%s)', (capabilities) => {
    picker(capabilities)
    expect(screen.queryByText(/Compatible con/)).toBeNull()
  })

  it.each(['es', 'en-us', 'pt-br', 'fr-fr'])('cambiar idioma conserva modelo y filtra la voz (%s)', (language) => {
    const languages = ['es', 'en-us', 'pt-br', 'fr-fr']
    const options: SynthesisOptions = {
      providers: [{ provider_id: 'local', display_name: 'Local', locality: 'local' }],
      models: [{ provider_id: 'local', model_id: 'multilingual', display_name: 'Multilingual', runtime_ready: true,
        languages, capabilities: ['cpu'], voices: languages.map((code) => ({ id: code + '-voice', name: code + ' voice', languages: [code] })) }],
      max_chars: 20000, speed: { min: 0.5, max: 2 },
    }
    function Harness() {
      const [preference, setPreference] = useState<SpeakPreference>({})
      return <SpeakVoicePicker id="languages" options={options} choice={resolveChoice(options, preference, 'es')} onChange={setPreference} />
    }
    render(<Harness />)
    const select = screen.getByRole<HTMLSelectElement>('combobox', { name: 'Idioma' })
    fireEvent.change(select, { target: { value: language } })
    expect(select.value).toBe(language)
    const voice = screen.getByRole<HTMLSelectElement>('combobox', { name: 'Voz' })
    expect(voice.value).toBe(language + '-voice')
    expect([...voice.options].map((item) => item.value)).toEqual([language + '-voice'])
    expect(screen.getByRole<HTMLSelectElement>('combobox', { name: 'Modelo' }).value).toBe('local:multilingual')
  })

  it('remoto conserva su aviso sin prometer CPU o GPU locales', () => {
    picker(['cpu', 'gpu'], 'cloud')
    expect(screen.getByText('Síntesis remota')).toBeDefined()
    expect(screen.queryByText(/Compatible con/)).toBeNull()
  })
})
