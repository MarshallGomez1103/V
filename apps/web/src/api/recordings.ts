import { translate } from '../i18n/i18n'
import { parseErrorCode } from './errors'
import { JOB_STATES, type JobState } from './jobs'
import { describeProjectError, ProjectError } from './projects'

/** Una grabación del proyecto con su último trabajo (`GET /api/projects/{id}/recordings`). */
export interface Recording {
  media_asset_id: string
  filename: string
  media_type: string | null
  duration_ms: number | null
  created_at: string
  latest_job: {
    id: string
    state: JobState
    transcript_id: string | null
    model_id: string | null
    created_at: string
  } | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function nullableString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function toLatestJob(value: unknown): Recording['latest_job'] {
  if (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.state === 'string' &&
    (JOB_STATES as readonly string[]).includes(value.state) &&
    typeof value.created_at === 'string'
  ) {
    return {
      id: value.id,
      state: value.state as JobState,
      transcript_id: nullableString(value.transcript_id),
      model_id: nullableString(value.model_id),
      created_at: value.created_at,
    }
  }
  return null
}

function toRecording(value: unknown): Recording | null {
  if (
    !isRecord(value) ||
    typeof value.media_asset_id !== 'string' ||
    typeof value.filename !== 'string' ||
    typeof value.created_at !== 'string'
  ) {
    return null
  }
  return {
    media_asset_id: value.media_asset_id,
    filename: value.filename,
    media_type: nullableString(value.media_type),
    duration_ms:
      typeof value.duration_ms === 'number' && Number.isFinite(value.duration_ms)
        ? value.duration_ms
        : null,
    created_at: value.created_at,
    latest_job: toLatestJob(value.latest_job),
  }
}

/** Grabaciones del proyecto en orden de importación. */
export async function fetchRecordings(projectId: string, signal?: AbortSignal): Promise<Recording[]> {
  const response = await fetch('/api/projects/' + encodeURIComponent(projectId) + '/recordings', {
    headers: { Accept: 'application/json' },
    ...(signal ? { signal } : {}),
  })
  const body: unknown = await response.json().catch(() => undefined)

  if (!response.ok) {
    const code = parseErrorCode(JSON.stringify(body)) ?? 'http_' + response.status
    throw new ProjectError(code, describeProjectError(code))
  }

  const list = isRecord(body) && Array.isArray(body.recordings) ? body.recordings : undefined
  const recordings = list?.map(toRecording)
  if (!recordings || recordings.some((item) => item === null)) {
    throw new ProjectError('invalid_response', translate('err.project.invalid_recordings'))
  }
  return recordings as Recording[]
}
