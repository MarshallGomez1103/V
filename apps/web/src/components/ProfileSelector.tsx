import { useEffect, useId, useState } from 'react'

import {
  getQualityProfiles,
  type QualityProfilesPayload,
} from '../api/qualityProfiles'
import './ProfileSelector.css'

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
    return <p className="profile-selector-status">Cargando perfiles…</p>
  }
  if (state.phase === 'error') {
    return (
      <p className="profile-selector-status" role="alert">
        {state.message}
      </p>
    )
  }

  const { payload } = state
  const selected = value ?? payload.default
  const recommendation = payload.recommendation

  return (
    <fieldset className="profile-selector" disabled={disabled}>
      <legend className="profile-selector-legend">Perfil de calidad</legend>
      {payload.profiles.map((profile) => (
        <label key={profile.name} className="profile-selector-option">
          <input
            type="radio"
            name={name}
            checked={selected === profile.name}
            onChange={() => {
              onChange(profile.name)
            }}
          />
          <span>
            <strong>{profile.label}</strong>
            {recommendation.profile === profile.name ? (
              <span className="profile-selector-badge">Medido</span>
            ) : null}
            <span className="profile-selector-description">
              {profile.description}
            </span>
          </span>
        </label>
      ))}
      <p className="profile-selector-note" data-testid="profile-recommendation">
        {recommendation.measured
          ? 'Recomendación (solo con mediciones reales): ' +
            recommendation.evidence +
            (recommendation.synthetic ? ' Orientativo, no representa audio real.' : '')
          : 'No hay perfil recomendado (' + recommendation.evidence + ').'}
      </p>
      <p className="profile-selector-note">
        Solo afecta a Faster Whisper; whisper.cpp y los motores en la nube lo
        ignoran.
      </p>
    </fieldset>
  )
}
