/**
 * Cliente de `GET /api/quality-profiles` (S13.02/S13.03/S13.11).
 * Ver docs/quality-profiles.md. La recomendación viene solo de mediciones
 * reales; sin medición el backend lo dice y no recomienda nada.
 */
import { readErrorCode } from './errors'

export interface VadParameters {
  threshold: number
  min_speech_duration_ms: number
  min_silence_duration_ms: number
  speech_pad_ms: number
}

export interface QualityProfileParameters {
  name: string
  version: number
  beam_size: number
  temperature: number[]
  condition_on_previous_text: boolean
  no_speech_threshold: number
  /** `null`: VAD apagado. */
  vad: VadParameters | null
}

export interface QualityProfile {
  name: string
  label: string
  description: string
  parameters: QualityProfileParameters
}

export interface ProfileRecommendation {
  language: string | null
  /** Mejor perfil medido, o `null` si no hay medición. */
  profile: string | null
  measured: boolean
  evidence: string
  synthetic: boolean
  unmeasured_profiles: string[]
}

export interface QualityProfilesPayload {
  default: string
  profiles: QualityProfile[]
  recommendation: ProfileRecommendation
}

export class QualityProfilesError extends Error {
  readonly code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = 'QualityProfilesError'
    this.code = code
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isProfile(value: unknown): value is QualityProfile {
  return (
    isRecord(value) &&
    typeof value.name === 'string' &&
    typeof value.label === 'string' &&
    typeof value.description === 'string' &&
    isRecord(value.parameters)
  )
}

function isRecommendation(value: unknown): value is ProfileRecommendation {
  return (
    isRecord(value) &&
    (value.profile === null || typeof value.profile === 'string') &&
    typeof value.measured === 'boolean' &&
    typeof value.evidence === 'string' &&
    typeof value.synthetic === 'boolean' &&
    Array.isArray(value.unmeasured_profiles)
  )
}

function isPayload(value: unknown): value is QualityProfilesPayload {
  return (
    isRecord(value) &&
    typeof value.default === 'string' &&
    Array.isArray(value.profiles) &&
    value.profiles.every(isProfile) &&
    isRecommendation(value.recommendation)
  )
}

export async function getQualityProfiles(
  language?: string | null,
  signal?: AbortSignal,
): Promise<QualityProfilesPayload> {
  const query = language ? '?language=' + encodeURIComponent(language) : ''
  const response = await fetch('/api/quality-profiles' + query, {
    headers: { Accept: 'application/json' },
    ...(signal ? { signal } : {}),
  })
  let body: unknown
  try {
    body = (await response.json()) as unknown
  } catch {
    body = undefined
  }
  if (!response.ok) {
    throw new QualityProfilesError(
      readErrorCode(body) ?? 'http_' + String(response.status),
      'No se pudieron consultar los perfiles de calidad.',
    )
  }
  if (!isPayload(body)) {
    throw new QualityProfilesError(
      'invalid_response',
      'La API devolvió perfiles de calidad con un formato inesperado.',
    )
  }
  return body
}
