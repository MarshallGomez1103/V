import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { SynthesisOptions, SynthesisView } from '../api/synthesis'
import { setLang } from '../i18n/i18n'
import { resolveChoice } from '../lib/speakChoice'
import { SpeakResult } from './SpeakResult'
import { SpeakVoicePicker } from './SpeakVoicePicker'

afterEach(cleanup)

const OPTIONS: SynthesisOptions = {
  providers: [
    { provider_id: 'compatible-remote', display_name: 'Remote', locality: 'cloud' },
    { provider_id: 'compatible-loopback', display_name: 'Loopback', locality: 'local' },
  ],
  models: ['compatible-loopback', 'compatible-remote'].map((provider_id) => ({
    provider_id,
    model_id: 'voice-model',
    display_name: provider_id,
    runtime_ready: true,
    languages: ['es'],
    voices: [{ id: 'voice', name: 'Voice', languages: ['es'] }],
  })),
  max_chars: 100,
  speed: { min: 0.5, max: 2 },
}

function picker(provider: string, disabled = false, options = OPTIONS, onChange = vi.fn()) {
  return (
    <SpeakVoicePicker
      id="test-voice"
      options={options}
      choice={resolveChoice(options, { model: provider + ':voice-model' }, 'es')}
      disabled={disabled}
      onChange={onChange}
    />
  )
}

const WARNINGS = {
  es: 'Al escuchar una muestra o generar audio, el texto se enviará fuera de este equipo al proveedor seleccionado.',
  en: 'When you hear a sample or generate audio, the text will be sent outside this computer to the selected provider.',
}

describe('SpeakVoicePicker: cloud locality', () => {
  it('labels remote choices before selection and keeps loopback unmarked', () => {
    render(picker('compatible-loopback'))

    expect(screen.getByRole('option', { name: 'compatible-remote · CLOUD' })).toBeDefined()
    expect(screen.getByRole('option', { name: 'compatible-loopback' })).toBeDefined()
    expect(screen.queryByText('CLOUD', { selector: '.cds--tag *' })).toBeNull()
    expect(screen.queryByText(WARNINGS.es)).toBeNull()
  })

  it.each(['es', 'en'] as const)('warns about text leaving the computer in %s even while disabled', (lang) => {
    setLang(lang)
    render(picker('compatible-remote', true))

    expect(screen.getByText('CLOUD', { selector: '.cds--tag *' })).toBeDefined()
    expect(screen.getByText(WARNINGS[lang])).toBeDefined()
    expect(screen.getByRole<HTMLSelectElement>('combobox', { name: lang === 'es' ? 'Modelo' : 'Model' }).disabled).toBe(true)
  })

  it('updates the warning after an explicit model change and removes it when returning local', () => {
    const onChange = vi.fn()
    const { rerender } = render(picker('compatible-loopback', false, OPTIONS, onChange))

    fireEvent.change(screen.getByLabelText('Modelo'), { target: { value: 'compatible-remote:voice-model' } })

    expect(onChange).toHaveBeenCalledExactlyOnceWith({ model: 'compatible-remote:voice-model', speed: 1 })
    rerender(picker('compatible-remote'))
    expect(screen.getByText(WARNINGS.es)).toBeDefined()
    rerender(picker('compatible-loopback'))
    expect(screen.queryByText(WARNINGS.es)).toBeNull()
  })

  it('uses provider locality rather than a compatible provider name', () => {
    const options = { ...OPTIONS, providers: OPTIONS.providers.map((provider) => ({ ...provider, locality: 'local' })) }
    render(picker('compatible-remote', false, options))

    expect(screen.getByRole('option', { name: 'compatible-remote' })).toBeDefined()
    expect(screen.queryByText(WARNINGS.es)).toBeNull()
  })
})

const RUNNING: SynthesisView = {
  id: 'test-job',
  state: 'RUNNING',
  progress: 0.5,
  chunks_done: 1,
  chunks_total: 2,
  error_code: null,
  created_at: '2026-10-15T12:00:00Z',
  updated_at: '2026-10-15T12:00:00Z',
  started_at: '2026-10-15T12:00:00Z',
  provider_id: 'compatible-remote',
  model_id: 'voice-model',
  voice_id: 'voice',
  language: null,
  speed: 1,
  text_length: 4,
  text_preview: 'Test',
  audio: null,
}

function result(job: SynthesisView | null, locality?: string) {
  return (
    <SpeakResult
      job={job}
      {...(locality === undefined ? {} : { locality })}
      reused={false}
      voiceName="Voice"
      streamError={null}
      onCancel={vi.fn()}
      onReconnect={vi.fn()}
    />
  )
}

describe('SpeakResult: cloud locality', () => {
  it.each(['es', 'en'] as const)('marks remote synthesis before and during the job in %s', (lang) => {
    setLang(lang)
    const { rerender } = render(result(null, 'cloud'))
    const warning = lang === 'es'
      ? 'Este trabajo usa un proveedor remoto que procesa el texto fuera de este equipo.'
      : 'This job uses a remote provider that processes the text outside this computer.'

    expect(screen.getByText('CLOUD', { selector: '.cds--tag *' })).toBeDefined()
    expect(screen.getByText(warning)).toBeDefined()
    rerender(result(RUNNING, 'cloud'))
    expect(screen.getByText(warning)).toBeDefined()
    expect(screen.queryByText(/en este equipo|on this computer/u)).toBeNull()
  })

  it.each(['local', undefined])('does not label %s results as cloud or assume local processing', (locality) => {
    render(result(RUNNING, locality))

    expect(screen.queryByText('CLOUD', { selector: '.cds--tag *' })).toBeNull()
    expect(screen.queryByText(/en este equipo/u)).toBeNull()
  })
})
