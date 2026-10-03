import { useEffect, useId, useState } from 'react'
import { RadioButton, RadioButtonGroup, Tag } from '@carbon/react'

import {
  getQualityProfiles,
  type QualityProfilesPayload,
} from '../api/qualityProfiles'
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
  | { key: string; phase: 'error'; message: string }
  | { key: string; phase: 'ready'; payload: QualityProfilesPayload }

export function ProfileSelector({
  value,
  onChange,
  language = null,
  disabled = false,
}: ProfileSelectorProps) {
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
          message:
            error instanceof Error
              ? error.message
              : 'No se pudieron consultar los perfiles de calidad.',
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
        <Busy description="Cargando perfiles…" />
      </div>
    )
  }
  if (state.phase === 'error') {
    return <Notice kind="error" title={state.message} />
  }

  const { payload } = state
  const selected = value ?? payload.default
  const recommendation = payload.recommendation

  return (
    <div className="voz-profile">
      <RadioButtonGroup
        legendText="Perfil de calidad"
        name={name}
        orientation="vertical"
        valueSelected={selected}
        disabled={disabled}
        onChange={(next) => {
          onChange(String(next))
        }}
      >
        {payload.profiles.map((profile) => (
          <RadioButton
            key={profile.name}
            id={name + '-' + profile.name}
            value={profile.name}
            labelText={
              <span className="voz-profile__option">
                <span className="voz-profile__label">
                  <strong>{profile.label}</strong>
                  {recommendation.profile === profile.name ? (
                    <Tag type="green" size="sm">
                      Medido
                    </Tag>
                  ) : null}
                </span>
                <span className="voz-profile__description">
                  {profile.description}
                </span>
              </span>
            }
          />
        ))}
      </RadioButtonGroup>
      <p className="voz-field-note" data-testid="profile-recommendation">
        {recommendation.measured
          ? 'Recomendación (solo con mediciones reales): ' +
            recommendation.evidence +
            (recommendation.synthetic ? ' Orientativo, no representa audio real.' : '')
          : 'No hay perfil recomendado (' + recommendation.evidence + ').'}
      </p>
      <p className="voz-field-note">
        Solo afecta a Faster Whisper; whisper.cpp y los motores en la nube lo
        ignoran.
      </p>
    </div>
  )
}
