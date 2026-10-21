/**
 * Cliente tipado de `GET /api/transcription-options` (contrato B1 / S5.18).
 * Ver docs/api/transcription-options.md. El frontend solo conoce lo que
 * publica el contrato: nunca paths, manifests ni internals del proveedor.
 */

import { translate } from '../i18n/i18n'

/** Permite los valores documentados con autocompletado sin rechazar códigos futuros. */
type LooseUnion<T extends string> = T | (string & Record<never, never>)

export type BlockingReasonCode =
  | 'model_not_registered'
  | 'model_files_missing'
  | 'revision_unpinned'
  | 'runtime_unavailable'
  | 'execution_unavailable'
  | 'transcription_unavailable'

export type BlockingReason = LooseUnion<BlockingReasonCode>

export type InstallationStatus = LooseUnion<'registered' | 'not_registered'>

export interface ProcessingProfile {
  name: LooseUnion<'fast' | 'quality'>
  device_preference: LooseUnion<'gpu_preferred' | 'cpu_only'>
  gpu_precisions: string[]
  cpu_precision: string
}

export interface ExecutionDecision {
  device: LooseUnion<'cuda' | 'cpu'>
  precision: string
  fallback_reason: string | null
}

export interface Recommendation {
  recommended: boolean
  reason: string
}

export interface TranscriptionOption {
  option_id: string
  provider_id: string
  model_id: string
  source: string | null
  revision: string | null
  profile: ProcessingProfile | null
  display_name: string
  installation_status: InstallationStatus
  files_available: boolean
  runtime_available: boolean
  can_start: boolean
  capabilities: string[]
  execution: ExecutionDecision | null
  device_name: string | null
  recommendation: Recommendation | null
  blocking_reasons: BlockingReason[]
  /** `true` si la opción envía el audio fuera del equipo (docs/api/providers.md). */
  cloud?: boolean
}

export interface TranscriptionOptionsPayload {
  options: TranscriptionOption[]
}

export type TranscriptionOptionsErrorCode = LooseUnion<
  'transcription_options_unavailable' | 'http_error' | 'invalid_payload'
>

/** Error con código estable y mensaje seguro para mostrar al usuario. */
export class TranscriptionOptionsError extends Error {
  readonly code: TranscriptionOptionsErrorCode
  readonly status: number | null

  constructor(
    code: TranscriptionOptionsErrorCode,
    message: string,
    status: number | null = null,
  ) {
    super(message)
    this.name = 'TranscriptionOptionsError'
    this.code = code
    this.status = status
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function isProcessingProfile(value: unknown): value is ProcessingProfile {
  return (
    isRecord(value) &&
    typeof value.name === 'string' &&
    typeof value.device_preference === 'string' &&
    isStringArray(value.gpu_precisions) &&
    typeof value.cpu_precision === 'string'
  )
}

function isExecutionDecision(value: unknown): value is ExecutionDecision {
  return (
    isRecord(value) &&
    typeof value.device === 'string' &&
    typeof value.precision === 'string' &&
    isNullableString(value.fallback_reason)
  )
}

function isRecommendation(value: unknown): value is Recommendation {
  return (
    isRecord(value) &&
    typeof value.recommended === 'boolean' &&
    typeof value.reason === 'string'
  )
}

export function isTranscriptionOption(
  value: unknown,
): value is TranscriptionOption {
  if (!isRecord(value)) {
    return false
  }
  return (
    typeof value.option_id === 'string' &&
    typeof value.provider_id === 'string' &&
    typeof value.model_id === 'string' &&
    isNullableString(value.source) &&
    isNullableString(value.revision) &&
    (value.profile === null || isProcessingProfile(value.profile)) &&
    typeof value.display_name === 'string' &&
    typeof value.installation_status === 'string' &&
    typeof value.files_available === 'boolean' &&
    typeof value.runtime_available === 'boolean' &&
    typeof value.can_start === 'boolean' &&
    isStringArray(value.capabilities) &&
    (value.execution === null || isExecutionDecision(value.execution)) &&
    isNullableString(value.device_name) &&
    (value.recommendation === null || isRecommendation(value.recommendation)) &&
    isStringArray(value.blocking_reasons)
  )
}

export function isTranscriptionOptionsPayload(
  value: unknown,
): value is TranscriptionOptionsPayload {
  return (
    isRecord(value) &&
    Array.isArray(value.options) &&
    value.options.every(isTranscriptionOption)
  )
}

async function readErrorCode(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json()
    if (isRecord(body) && isRecord(body.detail)) {
      const code: unknown = body.detail.code
      return typeof code === 'string' ? code : null
    }
  } catch {
    // Cuerpo vacío o no JSON: se informa solo el estado HTTP.
  }
  return null
}

async function toHttpError(
  response: Response,
): Promise<TranscriptionOptionsError> {
  const code = await readErrorCode(response)
  if (response.status === 503 && code === 'transcription_options_unavailable') {
    return new TranscriptionOptionsError(
      code,
      translate('err.options.unavailable'),
      response.status,
    )
  }
  return new TranscriptionOptionsError(
    code ?? 'http_error',
    translate('err.options.http', { status: response.status }),
    response.status,
  )
}

export async function getTranscriptionOptions(
  signal?: AbortSignal,
): Promise<TranscriptionOptionsPayload> {
  const response = await fetch('/api/transcription-options', {
    headers: { Accept: 'application/json' },
    ...(signal ? { signal } : {}),
  })
  if (!response.ok) {
    throw await toHttpError(response)
  }
  const body: unknown = await response.json()
  if (!isTranscriptionOptionsPayload(body)) {
    throw new TranscriptionOptionsError(
      'invalid_payload',
      translate('err.options.invalid'),
    )
  }
  return body
}
