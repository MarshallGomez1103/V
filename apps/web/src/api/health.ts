export interface HealthPayload {
  status: string
  service?: string
  version?: string
}

function isHealthPayload(value: unknown): value is HealthPayload {
  if (typeof value !== 'object' || value === null) {
    return false
  }

  return 'status' in value && typeof value.status === 'string'
}

export async function getHealth(signal?: AbortSignal): Promise<HealthPayload> {
  const response = await fetch('/api/health', {
    headers: { Accept: 'application/json' },
    ...(signal ? { signal } : {}),
  })

  if (!response.ok) {
    throw new Error('Health check falló con estado ' + response.status + '.')
  }

  const body: unknown = await response.json()

  if (!isHealthPayload(body)) {
    throw new Error('La API devolvió un estado de salud inválido.')
  }

  return body
}
