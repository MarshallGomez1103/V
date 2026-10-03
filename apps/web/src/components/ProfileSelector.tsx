import { useEffect, useId, useState } from 'react'
import { RadioButton, RadioButtonGroup, Tag } from '@carbon/react'

import {
  getQualityProfiles,
  type QualityProfile,
  type QualityProfilesPayload,
} from '../api/qualityProfiles'
import { useI18n } from '../i18n/i18n'
import type { MessageKey } from '../i18n/messages'
import { InfoTip, Term } from './Hint'
import { Busy } from './Busy'
import { Notice } from './Notice'
import './ProfileSelector.scss'

export interface ProfileSelectorProps {
  /** Nombre del perfil elegido; `null` usa el perfil por defecto del backend. */
  value: string | null
  onChange: (profileName: string) => void
  /** Idioma elegido (`null` = autodetectado): decide qué recomendación hay medida. */
  language?: string | null
  disabled?: boolean
}

/** `key` es el idioma consultado: si no coincide con el actual, sigue cargando. */
type LoadResult =
  | { key: string; phase: 'error'; message: string | null }
  | { key: string; phase: 'ready'; payload: QualityProfilesPayload }

const KNOWN: Readonly<Record<string, { label: MessageKey; description: MessageKey }>> = {
  default: { label: 'profile.default.label', description: 'profile.default.description' },
  academic: { label: 'profile.academic.label', description: 'profile.academic.description' },
}

function TechnicalLine({ profile }: { profile: QualityProfile }) {
  const { t } = useI18n()
  const { parameters } = profile
  return (
    <span className="voz-profile__tech">
      <span>
        <Term definition="term.beam.def">{t('term.beam')}</Term>
        {': ' + String(parameters.beam_size)}
      </span>
      <span>
        <Term definition="term.vad.def">VAD</Term>
        {': ' + (parameters.vad === null ? t('profile.vad.off') : t('profile.vad.on'))}
      </span>
      <span>
        <Term definition="term.prevtext.def">{t('term.prevtext')}</Term>
        {': ' + (parameters.condition_on_previous_text ? t('common.yes') : t('common.no'))}
      </span>
    </span>
  )
}

export function ProfileSelector({
  value,
  onChange,
  language = null,
  disabled = false,
}: ProfileSelectorProps) {
  const { t } = useI18n()
  const name = useId()
  const key = language ?? ''
  const [result, setResult] = useState<LoadResult | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getQualityProfiles(language, controller.signal)
      .then((payload) => {
        setResult({ key, phase: 'ready', payload })
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return
        }
        setResult({
          key,
          phase: 'error',
          message: error instanceof Error ? error.message : null,
        })
      })
    return () => {
      controller.abort()
    }
  }, [language, key])

  const state = result?.key === key ? result : null

  if (state === null) {
    return (
      <div className="voz-profile" aria-live="polite">
        <Busy description={t('profile.loading')} />
      </div>
    )
  }
  if (state.phase === 'error') {
    return <Notice kind="error" title={state.message ?? t('err.profiles.load')} />
  }

  const { payload } = state
  const selected = value ?? payload.default
  const recommendation = payload.recommendation

  return (
    <div className="voz-profile">
      <RadioButtonGroup
        legendText={t('profile.legend')}
        name={name}
        orientation="vertical"
        valueSelected={selected}
        disabled={disabled}
        onChange={(next) => {
          onChange(String(next))
        }}
      >
        {payload.profiles.map((profile) => {
          const known = Object.hasOwn(KNOWN, profile.name) ? KNOWN[profile.name] : undefined
          return (
            <RadioButton
              key={profile.name}
              id={name + '-' + profile.name}
              value={profile.name}
              labelText={
                <span className="voz-profile__option">
                  <span className="voz-profile__label">
                    <strong>{known ? t(known.label) : profile.label}</strong>
                    {recommendation.profile === profile.name ? (
                      <Tag type="green" size="sm">
                        <Term definition="term.measured.def">{t('profile.measured')}</Term>
                      </Tag>
                    ) : null}
                  </span>
                  <span className="voz-profile__description">
                    {known ? t(known.description) : profile.description}
                  </span>
                </span>
              }
            />
          )
        })}
      </RadioButtonGroup>
      <ul className="voz-profile__techlist" aria-label={t('profile.tech')}>
        {payload.profiles.map((profile) => {
          const known = Object.hasOwn(KNOWN, profile.name) ? KNOWN[profile.name] : undefined
          return (
            <li key={profile.name}>
              <strong>{known ? t(known.label) : profile.label}</strong>
              <TechnicalLine profile={profile} />
            </li>
          )
        })}
      </ul>
      <div className="voz-field-note" data-testid="profile-recommendation">
        {recommendation.measured
          ? t('profile.recommended') +
            (recommendation.synthetic ? ' ' + t('profile.synthetic') : '')
          : t('profile.noRecommendation')}{' '}
        <InfoTip label="profile.evidence.label" align="top-start">
          <p>{recommendation.evidence}</p>
        </InfoTip>
      </div>
      <p className="voz-field-note">{t('profile.scope')}</p>
    </div>
  )
}
