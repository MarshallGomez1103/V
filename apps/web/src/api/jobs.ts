// ponytail: duplicado con api/jobEvents.ts hasta que root unifique
export const JOB_STATES = [
  'QUEUED',
  'PROBING',
  'PREPROCESSING',
  'TRANSCRIBING',
  'ALIGNING',
  'DIARIZING',
  'MERGING',
  'PERSISTING',
  'COMPLETED',
  'FAILED',
  'CANCELLING',
  'CANCELLED',
] as const

export type JobState = (typeof JOB_STATES)[number]

export const PROCESSABLE_STATES: ReadonlySet<JobState> = new Set<JobState>([
  'QUEUED',
  'PROBING',
  'PREPROCESSING',
  'TRANSCRIBING',
  'ALIGNING',
  'DIARIZING',
  'MERGING',
  'PERSISTING',
])

export interface JobSelection {
  option_id: string
  provider_id: string
  model_id: string
  source?: string
  revision?: string | null
  profile?: { name?: string; [key: string]: unknown }
  execution?: { device?: string; [key: string]: unknown }
  language?: string | null
  // S13.02: receta de decodificación completa con la que se creó el job, y el
  // glosario congelado en ese momento (ausentes en jobs anteriores).
  quality_profile?: { name: string; version: number; [key: string]: unknown } | null
  glossary?: string[]
}

export interface JobView {
  id: string
  project_id: string
  media_asset_id: string
  state: JobState
  progress: number
  error_code: string | null
  transcript_id: string | null
  // Si la diarización falló, el transcript existe igual y aquí va el código.
  diarization_error_code?: string | null
  selection?: JobSelection
  created_at: string
  updated_at: string
}

export interface CreateJobInput {
  project_id: string
  media_asset_id: string
  option_id: string
  language: string | null
  // Perfil de calidad (S13.02); ausente = `default`.
  profile?: string
  // Diarización opcional (S6); ausente o enabled=false = desactivada.
  diarization?: {
    enabled: boolean
    speakers: { exact?: number; minimum?: number; maximum?: number }
  }
}

export interface TranscriptWord {
  start_ms: number
  end_ms: number
  text: string
  speaker_id: string | null
}

export interface SegmentQuality {
  flags: string[]
  avg_logprob: number | null
}

export interface TranscriptSegment {
  id: string
  start_ms: number
  end_ms: number
  text: string
  edited: boolean
  revision: number
  speaker_id: string | null
  // S13.04/S13.12: pistas de calidad no destructivas; el texto no cambia.
  quality: SegmentQuality
  // S7.04/S7.05: vacío si el segmento se editó o el modelo no dio palabras.
  words: TranscriptWord[]
}

export class JobApiError extends Error {
  code: string
  blockingReasons?: string[]

  constructor(code: string, message: string, blockingReasons?: string[]) {
    super(message)
    this.name = 'JobApiError'
    this.code = code
    if (blockingReasons) {
      this.blockingReasons = blockingReasons
    }
  }
}

const ERROR_MESSAGES: Record<string, string> = {
  project_not_found: 'El proyecto ya no existe.',
  media_asset_not_found: 'La grabación ya no existe en el proyecto.',
  option_unknown: 'La opción de transcripción elegida no está disponible.',
  option_not_startable:
    'Esta opción todavía no se puede iniciar en este equipo.',
  job_already_active: 'Ya hay una transcripción en curso para esta grabación.',
  job_terminal: 'La transcripción ya terminó y no se puede cancelar.',
  quality_profile_unknown: 'El perfil de calidad elegido no existe.',
  transcript_not_found: 'La transcripción ya no existe.',
  invalid_response: 'La API devolvió una respuesta inesperada.',
}

export function messageForCode(code: string): string {
  return (
    ERROR_MESSAGES[code] ??
    'No se pudo completar la operación (código ' + code + ').'
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function isJobState(value: unknown): value is JobState {
  return (
    typeof value === 'string' && (JOB_STATES as readonly string[]).includes(value)
  )
}

export function isJobView(value: unknown): value is JobView {
  if (!isRecord(value)) {
    return false
  }

  return (
    typeof value.id === 'string' &&
    typeof value.project_id === 'string' &&
    typeof value.media_asset_id === 'string' &&
    isJobState(value.state) &&
    typeof value.progress === 'number' &&
    isNullableString(value.error_code) &&
    isNullableString(value.transcript_id) &&
    (value.selection === undefined || isRecord(value.selection)) &&
    typeof value.created_at === 'string' &&
    typeof value.updated_at === 'string'
  )
}

function isWord(value: unknown): value is TranscriptWord {
  return (
    isRecord(value) &&
    typeof value.start_ms === 'number' &&
    typeof value.end_ms === 'number' &&
    typeof value.text === 'string' &&
    isNullableString(value.speaker_id)
  )
}

function isQuality(value: unknown): value is SegmentQuality {
  return (
    isRecord(value) &&
    Array.isArray(value.flags) &&
    value.flags.every((flag) => typeof flag === 'string') &&
    (value.avg_logprob === null || typeof value.avg_logprob === 'number')
  )
}

function isSegment(value: unknown): value is TranscriptSegment {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.start_ms === 'number' &&
    typeof value.end_ms === 'number' &&
    typeof value.text === 'string' &&
    typeof value.edited === 'boolean' &&
    typeof value.revision === 'number' &&
    isNullableString(value.speaker_id) &&
    isQuality(value.quality) &&
    Array.isArray(value.words) &&
    value.words.every(isWord)
  )
}

function isSegmentsPayload(
  value: unknown,
): value is { segments: TranscriptSegment[] } {
  return (
    isRecord(value) &&
    Array.isArray(value.segments) &&
    value.segments.every(isSegment)
  )
}

async function errorFromResponse(response: Response): Promise<JobApiError> {
  const body: unknown = await response.json().catch(() => null)
  const detail = isRecord(body) ? body.detail : null

  if (isRecord(detail) && typeof detail.code === 'string') {
    const reasons = Array.isArray(detail.blocking_reasons)
      ? detail.blocking_reasons.filter(
          (reason): reason is string => typeof reason === 'string',
        )
      : undefined
    return new JobApiError(detail.code, messageForCode(detail.code), reasons)
  }

  const code = 'http_' + response.status
  return new JobApiError(
    code,
    'La API respondió con estado ' + response.status + '.',
  )
}

async function request<T>(
  url: string,
  init: RequestInit,
  guard: (value: unknown) => value is T,
): Promise<T> {
  const response = await fetch(url, init)

  if (!response.ok) {
    throw await errorFromResponse(response)
  }

  const body: unknown = await response.json()

  if (!guard(body)) {
    throw new JobApiError(
      'invalid_response',
      messageForCode('invalid_response'),
    )
  }

  return body
}

const JSON_HEADERS = { Accept: 'application/json' }

export function createJob(
  input: CreateJobInput,
  signal?: AbortSignal,
): Promise<JobView> {
  return request(
    '/api/jobs',
    {
      method: 'POST',
      headers: { ...JSON_HEADERS, 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
      ...(signal ? { signal } : {}),
    },
    isJobView,
  )
}

export function getJob(id: string, signal?: AbortSignal): Promise<JobView> {
  return request(
    '/api/jobs/' + encodeURIComponent(id),
    { headers: JSON_HEADERS, ...(signal ? { signal } : {}) },
    isJobView,
  )
}

export function cancelJob(id: string): Promise<JobView> {
  return request(
    '/api/jobs/' + encodeURIComponent(id) + '/cancel',
    { method: 'POST', headers: JSON_HEADERS },
    isJobView,
  )
}

export async function getSegments(
  transcriptId: string,
  signal?: AbortSignal,
): Promise<TranscriptSegment[]> {
  const payload = await request(
    '/api/transcripts/' + encodeURIComponent(transcriptId) + '/segments',
    { headers: JSON_HEADERS, ...(signal ? { signal } : {}) },
    isSegmentsPayload,
  )
  return payload.segments
}
