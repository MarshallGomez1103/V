import { isAbortError, readErrorCode } from './errors'
import { listJobs, type JobState, JOB_STATES } from './jobs'
import { describeProjectError, listProjects, ProjectError } from './projects'

/** Una fila de la biblioteca: un proyecto con su medio y su último trabajo. */
export interface LibraryItem {
  project_id: string
  name: string
  created_at: string
  media: { media_asset_id: string; filename: string; duration_ms: number | null } | null
  latest_job: {
    id: string
    state: JobState
    transcript_id: string | null
    model_id: string | null
    created_at: string
  } | null
  /** `null` = el servidor no lo informa (versión sin `/api/library`). */
  speaker_count: number | null
  segment_count: number | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function nullableNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function nullableString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function toMedia(value: unknown): LibraryItem['media'] {
  if (
    isRecord(value) &&
    typeof value.media_asset_id === 'string' &&
    typeof value.filename === 'string'
  ) {
    return {
      media_asset_id: value.media_asset_id,
      filename: value.filename,
      duration_ms: nullableNumber(value.duration_ms),
    }
  }
  return null
}

function toLatestJob(value: unknown): LibraryItem['latest_job'] {
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

function toItem(value: unknown): LibraryItem | null {
  if (
    !isRecord(value) ||
    typeof value.project_id !== 'string' ||
    typeof value.name !== 'string' ||
    typeof value.created_at !== 'string'
  ) {
    return null
  }
  return {
    project_id: value.project_id,
    name: value.name,
    created_at: value.created_at,
    media: toMedia(value.media),
    latest_job: toLatestJob(value.latest_job),
    speaker_count: nullableNumber(value.speaker_count),
    segment_count: nullableNumber(value.segment_count),
  }
}

/** Biblioteca armada con lo que ya existía (proyectos + trabajos) si el servidor es anterior. */
async function composeLibrary(signal?: AbortSignal): Promise<LibraryItem[]> {
  const projects = await listProjects(signal)
  return Promise.all(
    projects.map(async (project): Promise<LibraryItem> => {
      const jobs = await listJobs(project.id, signal)
      const latest = [...jobs].sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
      return {
        project_id: project.id,
        name: project.name,
        created_at: project.created_at,
        // ponytail: sin /api/library no se conoce el nombre del archivo ni la duración.
        media: latest
          ? { media_asset_id: latest.media_asset_id, filename: project.name, duration_ms: null }
          : null,
        latest_job: latest
          ? {
              id: latest.id,
              state: latest.state,
              transcript_id: latest.transcript_id,
              model_id: latest.selection?.model_id ?? null,
              created_at: latest.created_at,
            }
          : null,
        speaker_count: null,
        segment_count: null,
      }
    }),
  )
}

/** `GET /api/library`; si el servidor aún no lo tiene (404/405/501), se compone en el cliente. */
export async function fetchLibrary(signal?: AbortSignal): Promise<LibraryItem[]> {
  let response: Response
  try {
    response = await fetch('/api/library', {
      headers: { Accept: 'application/json' },
      ...(signal ? { signal } : {}),
    })
  } catch (error) {
    if (isAbortError(error)) {
      throw error
    }
    return composeLibrary(signal)
  }
  if ([404, 405, 501].includes(response.status)) {
    return composeLibrary(signal)
  }
  if (!response.ok) {
    throw new ProjectError('http_' + response.status, describeProjectError('http_' + response.status))
  }
  const body: unknown = await response.json().catch(() => null)
  const raw = isRecord(body) ? body.items : null
  if (!Array.isArray(raw)) {
    throw new ProjectError('invalid_response', describeProjectError('invalid_list'))
  }
  const items = raw.map(toItem)
  if (items.some((item) => item === null)) {
    throw new ProjectError('invalid_response', describeProjectError('invalid_list'))
  }
  return items as LibraryItem[]
}

async function failFrom(response: Response): Promise<never> {
  const body: unknown = await response.json().catch(() => null)
  const code = readErrorCode(body) ?? 'http_' + response.status
  throw new ProjectError(code, describeProjectError(code))
}

/** Renombra un proyecto (422 `project_name_invalid` si el nombre no vale). */
export async function renameProject(
  projectId: string,
  name: string,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch('/api/projects/' + encodeURIComponent(projectId), {
    method: 'PATCH',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
    ...(signal ? { signal } : {}),
  })
  if (!response.ok) {
    return failFrom(response)
  }
}

/** Elimina el proyecto entero: trabajos, transcripciones y la copia del audio guardada en VOZ. */
export async function deleteProject(projectId: string, signal?: AbortSignal): Promise<void> {
  const response = await fetch('/api/projects/' + encodeURIComponent(projectId), {
    method: 'DELETE',
    headers: { Accept: 'application/json', 'X-VOZ-Action': 'delete-project' },
    ...(signal ? { signal } : {}),
  })
  if (!response.ok) {
    return failFrom(response)
  }
}
