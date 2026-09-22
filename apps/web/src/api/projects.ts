import { readErrorCode } from './errors'

export interface Project {
  id: string
  name: string
  created_at: string
}

export class ProjectError extends Error {
  readonly code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = 'ProjectError'
    this.code = code
  }
}

const PROJECT_MESSAGES: Record<string, string> = {
  project_name_invalid: 'El nombre del proyecto no es válido.',
  project_not_found: 'El proyecto ya no existe.',
}

export function describeProjectError(code: string): string {
  return PROJECT_MESSAGES[code] ?? 'No se pudo completar la operación con el proyecto.'
}

function isProject(value: unknown): value is Project {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    typeof value.id === 'string' &&
    'name' in value &&
    typeof value.name === 'string' &&
    'created_at' in value &&
    typeof value.created_at === 'string'
  )
}

async function readBody(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown
  } catch {
    return undefined
  }
}

async function throwFromResponse(response: Response): Promise<never> {
  const code = readErrorCode(await readBody(response)) ?? 'http_' + response.status
  throw new ProjectError(code, describeProjectError(code))
}

export async function createProject(
  name: string,
  signal?: AbortSignal,
): Promise<Project> {
  const response = await fetch('/api/projects', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
    ...(signal ? { signal } : {}),
  })

  if (!response.ok) {
    return throwFromResponse(response)
  }

  const body = await readBody(response)

  if (!isProject(body)) {
    throw new ProjectError('invalid_response', 'La API devolvió un proyecto inválido.')
  }

  return body
}

export async function listProjects(signal?: AbortSignal): Promise<Project[]> {
  const response = await fetch('/api/projects', {
    headers: { Accept: 'application/json' },
    ...(signal ? { signal } : {}),
  })

  if (!response.ok) {
    return throwFromResponse(response)
  }

  const body = await readBody(response)

  if (
    typeof body !== 'object' ||
    body === null ||
    !('projects' in body) ||
    !Array.isArray(body.projects) ||
    !body.projects.every(isProject)
  ) {
    throw new ProjectError(
      'invalid_response',
      'La API devolvió una lista de proyectos inválida.',
    )
  }

  return body.projects
}
