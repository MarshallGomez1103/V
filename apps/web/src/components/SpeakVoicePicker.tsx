import type { CSSProperties } from 'react'
import { Button, Select, SelectItem } from '@carbon/react'

import type { SynthesisModel, SynthesisOptions } from '../api/synthesis'
import { localeOf, useI18n } from '../i18n/i18n'
import {
  modelKey,
  preferenceOf,
  SPEED_STEP,
  type SpeakChoice,
  type SpeakPreference,
} from '../lib/speakChoice'
import { CloudBadge } from './CloudBadge'
import { Notice } from './Notice'

interface SpeakVoicePickerProps {
  id: string
  options: SynthesisOptions
  choice: SpeakChoice
  disabled?: boolean
  onChange: (preference: SpeakPreference) => void
}

/** Nombre del idioma en el idioma de la interfaz; el código si el navegador no lo conoce. */
function useLanguageName() {
  const { lang } = useI18n()
  let names: Intl.DisplayNames | null = null
  try {
    names = new Intl.DisplayNames(localeOf(lang), { type: 'language' })
  } catch {
    names = null
  }
  return (code: string): string => {
    try {
      return names?.of(code) ?? code
    } catch {
      return code
    }
  }
}

function modelLabel(model: SynthesisModel, options: SynthesisOptions): string {
  const cloud = options.providers.find((provider) => provider.provider_id === model.provider_id)?.locality === 'cloud'
  return model.display_name + (cloud ? ' · CLOUD' : '')
}

/** Modelo, voz, idioma (si el modelo tiene varios) y velocidad; sin estado propio. */
export function SpeakVoicePicker({ id, options, choice, disabled = false, onChange }: SpeakVoicePickerProps) {
  const { t, lang } = useI18n()
  const languageName = useLanguageName()
  const { min, max } = options.speed
  const format = new Intl.NumberFormat(localeOf(lang), { minimumFractionDigits: 1, maximumFractionDigits: 1 })
  const speedText = t('speak.voice.speedValue', { speed: format.format(choice.speed) })
  const fill = max > min ? ((choice.speed - min) / (max - min)) * 100 : 0
  const multiLanguage = choice.model.languages.length > 1
  const cloud = options.providers.find((provider) => provider.provider_id === choice.model.provider_id)?.locality === 'cloud'
  return (
    <div className="voz-speak__selectors">
      <Select
        id={id + '-model'}
        labelText={t('speak.voice.model')}
        value={modelKey(choice.model)}
        disabled={disabled}
        helperText={
          choice.model.runtime_ready
            ? t('speak.voice.languages', {
                list: choice.model.languages.map(languageName).join(', '),
              })
            : t('speak.voice.notReady')
        }
        onChange={(event) => {
          // Otro modelo: voz e idioma se vuelven a resolver (la voz de uno no es la del otro).
          onChange({ model: event.target.value, speed: choice.speed })
        }}
      >
        {options.models.map((model) => (
          <SelectItem key={modelKey(model)} value={modelKey(model)} text={modelLabel(model, options)} />
        ))}
      </Select>
      {cloud ? (
        <Notice kind="warning" title={t('speak.cloud.title')} subtitle={t('speak.cloud.notice')}>
          <CloudBadge plain />
        </Notice>
      ) : null}
      {multiLanguage ? (
        <Select
          id={id + '-language'}
          labelText={t('speak.voice.language')}
          value={choice.language ?? ''}
          disabled={disabled}
          onChange={(event) => {
            onChange({ ...preferenceOf(choice), language: event.target.value })
          }}
        >
          {choice.model.languages.map((code) => (
            <SelectItem key={code} value={code} text={languageName(code)} />
          ))}
        </Select>
      ) : null}
      <Select
        id={id + '-voice-select'}
        labelText={t('speak.voice.voice')}
        value={choice.voice?.id ?? ''}
        disabled={disabled || choice.voices.length === 0}
        onChange={(event) => {
          onChange({ ...preferenceOf(choice), voice: event.target.value })
        }}
      >
        {choice.voices.map((voice) => (
          <SelectItem key={voice.id} value={voice.id} text={voice.name} />
        ))}
      </Select>
      <div className="voz-speak__speed">
        <div className="voz-speak__speed-head">
          <label className="cds--label" htmlFor={id + '-speed'}>
            {t('speak.voice.speed')}
          </label>
          <output htmlFor={id + '-speed'} className="voz-speak__speed-value">
            {speedText}
          </output>
        </div>
        <div className="voz-speak__speed-row">
          <input
            id={id + '-speed'}
            type="range"
            className="voz-range voz-speak__range"
            min={min}
            max={max}
            step={SPEED_STEP}
            value={choice.speed}
            disabled={disabled}
            style={{ '--voz-fill': String(fill) + '%' } as CSSProperties}
            aria-valuetext={speedText}
            aria-describedby={id + '-speed-hint'}
            onChange={(event) => {
              onChange({ ...preferenceOf(choice), speed: Number(event.currentTarget.value) })
            }}
          />
          <Button
            kind="ghost"
            size="sm"
            disabled={disabled || choice.speed === 1}
            onClick={() => {
              onChange({ ...preferenceOf(choice), speed: 1 })
            }}
          >
            {t('speak.voice.speedReset')}
          </Button>
        </div>
        <p id={id + '-speed-hint'} className="voz-field-note">
          {t('speak.voice.speedHint', { min: format.format(min), max: format.format(max) })}
        </p>
      </div>
    </div>
  )
}
