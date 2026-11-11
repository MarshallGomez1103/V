import { translate } from '../i18n/i18n'
import { MESSAGES, type MessageKey } from '../i18n/messages'
import { readErrorCode } from './errors'
import { JOB_STATES, type CreateJobInput, type JobState } from './jobs'

export type QueueItemStatus = 'pending' | 'running' | 'done' | 'error' | 'cancelled'

const ITEM_STATUSES: readonly string[] = ['pending', 'running', 'done', 'error', 'cancelled']

export interface QueueItem {
  position: number
  media_asset_id: string
  filename: string
  job_id: string
  status: QueueItemStatus
  job_state: JobState
  /** 0..1 del trabajo del ítem. */
  progress: number
  error_code: string | null
  transcript_id: string | null
}

/** Grabación que la cola no incluyó; `reason` es un código estable (p. ej. `already_transcribed`). */
export interface SkippedRecording {
  media_asset_id: string
  filename: string
  reason: string
}

export interface QueueCounts {
  total: number
  pending: number
  running: number
  done: number
  error: number
  cancelled: number
  skipped: number
}

/** Vista de una cola de transcripción (docs/api/transcription-queue.md). */
export interface QueueView {
  id: string
  project_id: string
  created_at: string
  state: 'running' | 'finished'
  /** 0..1 de toda la cola. */
  progress: number
  counts: QueueCounts
  items: QueueItem[]
  skipped: SkippedRecording[]
}

export type StartQueueInput = Pick<CreateJobInput, 'option_id' | 'language' | 'diarization'>

export class QueueError extends Error {
  readonly code: string
  /** Omitidas que el servidor adjunta al rechazar una cola vacía. */
  readonly skipped: SkippedRecording[]

  constructor(code: string, message: string, skipped: SkippedRecording[] = []) {
    super(message)
    this.name = 'QueueError'
    this.code = code
    this.skipped = skipped
  }
}

// Los códigos de la opción y de los recursos ya tienen mensaje en otros catálogos.
const ERROR_PREFIXES = ['err.queue.', 'err.job.', 'err.speaker.'] as const

export function describeQueueError(code: string): string {
  for (const prefix of ERROR_PREFIXES) {
    if (Object.hasOwn(MESSAGES, prefix + code)) {
      return translate((prefix + code) as MessageKey)
    }
  }
  return translate('err.queue.generic', { code })
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function toItem(value: unknown): QueueItem | null {
  if (
    !isRecord(value) ||
    typeof value.position !== 'number' ||
    typeof value.media_asset_id !== 'string' ||
    typeof value.filename !== 'string' ||
    typeof value.job_id !== 'string' ||
    typeof value.status !== 'string' ||
    !ITEM_STATUSES.includes(value.status) ||
    typeof value.job_state !== 'string' ||
    !(JOB_STATES as readonly string[]).includes(value.job_state) ||
    typeof value.progress !== 'number' ||
    !isNullableString(value.error_code) ||
    !isNullableString(value.transcript_id)
  ) {
    return null
  }
  return value as unknown as QueueItem
}

function toSkipped(value: unknown): SkippedRecording | null {
  return isRecord(value) &&
    typeof value.media_asset_id === 'string' &&
    typeof value.filename === 'string' &&
    typeof value.reason === 'string'
    ? { media_asset_id: value.media_asset_id, filename: value.filename, reason: value.reason }
    : null
}

function toList<T>(value: unknown, convert: (item: unknown) => T | null): T[] | null {
  const list = Array.isArray(value) ? value.map(convert) : null
  return list && list.every((entry) => entry !== null) ? (list) : null
}

function toCounts(value: unknown): QueueCounts | null {
  const keys = ['total', 'pending', 'running', 'done', 'error', 'cancelled', 'skipped']
  return isRecord(value) && keys.every((key) => typeof value[key] === 'number')
    ? (value as unknown as QueueCounts)
    : null
}

function toQueue(value: unknown): QueueView | null {
  if (!isRecord(value)) {
    return null
  }
  const items = toList(value.items, toItem)
  const skipped = toList(value.skipped, toSkipped)
  const counts = toCounts(value.counts)
  if (
    typeof value.id !== 'string' ||
    typeof value.project_id !== 'string' ||
    typeof value.created_at !== 'string' ||
    (value.state !== 'running' && value.state !== 'finished') ||
    typeof value.progress !== 'number' ||
    !items ||
    !skipped ||
    !counts
  ) {
    return null
  }
  return {
    id: value.id,
    project_id: value.project_id,
    created_at: value.created_at,
    state: value.state,
    progress: value.progress,
    counts,
    items,
    skipped,
  }
}

function invalid(): QueueError {
  return new QueueError('invalid_response', describeQueueError('invalid_response'))
}

async function call(url: string, init: RequestInit): Promise<unknown> {
  const response = await fetch(url, {
    ...init,
    headers: { Accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}) },
  })
  const body: unknown = await response.json().catch(() => undefined)
  if (!response.ok) {
    const code = readErrorCode(body) ?? 'http_' + response.status
    const detail = isRecord(body) && isRecord(body.detail) ? body.detail : undefined
    throw new QueueError(code, describeQueueError(code), toList(detail?.skipped, toSkipped) ?? [])
  }
  return body
}

/** Crea la cola del proyecto (`POST /api/projects/{id}/transcription-queue`). */
export async function startQueue(
  projectId: string,
  input: StartQueueInput,
  signal?: AbortSignal,
): Promise<QueueView> {
  const queue = toQueue(
    await call('/api/projects/' + encodeURIComponent(projectId) + '/transcription-queue', {
      method: 'POST',
      body: JSON.stringify(input),
      ...(signal ? { signal } : {}),
    }),
  )
  if (!queue) {
    throw invalid()
  }
  return queue
}

/** La cola más reciente del proyecto, o `null` si nunca se creó una. */
export async function getProjectQueue(projectId: string, signal?: AbortSignal): Promise<QueueView | null> {
  const body = await call('/api/projects/' + encodeURIComponent(projectId) + '/transcription-queue', {
    ...(signal ? { signal } : {}),
  })
  const raw = isRecord(body) ? body.queue : undefined
  if (raw === null) {
    return null
  }
  const queue = toQueue(raw)
  if (!queue) {
    throw invalid()
  }
  return queue
}

/** Cancela los ítems pendientes y el que corre (`POST /api/transcription-queues/{id}/cancel`). */
export async function cancelQueue(queueId: string, signal?: AbortSignal): Promise<QueueView> {
  const queue = toQueue(
    await call('/api/transcription-queues/' + encodeURIComponent(queueId) + '/cancel', {
      method: 'POST',
      ...(signal ? { signal } : {}),
    }),
  )
  if (!queue) {
    throw invalid()
  }
  return queue
}
