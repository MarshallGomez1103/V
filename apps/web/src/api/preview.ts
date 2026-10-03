/**
 * `GET /api/jobs/{id}/preview?after_ms=<n>`: segmentos ya confirmados mientras el motor
 * transcribe, antes de que exista el transcript final. Si el backend aún no lo ofrece
 * (404/405/501) se devuelve `null` y la UI simplemente no muestra vista previa.
 */
export interface PreviewSegment {
  start_ms: number
  end_ms: number
  text: string
}

function isPreviewSegment(value: unknown): value is PreviewSegment {
  return (
    typeof value === 'object' &&
    value !== null &&
    'start_ms' in value &&
    typeof value.start_ms === 'number' &&
    'end_ms' in value &&
    typeof value.end_ms === 'number' &&
    'text' in value &&
    typeof value.text === 'string'
  )
}

export async function getJobPreview(
  jobId: string,
  afterMs: number,
  signal?: AbortSignal,
): Promise<PreviewSegment[] | null> {
  const response = await fetch(
    '/api/jobs/' + encodeURIComponent(jobId) + '/preview?after_ms=' + String(Math.max(0, Math.floor(afterMs))),
    { headers: { Accept: 'application/json' }, ...(signal ? { signal } : {}) },
  )
  if (response.status === 404 || response.status === 405 || response.status === 501) {
    return null
  }
  if (!response.ok) {
    throw new Error('preview_http_' + String(response.status))
  }
  const body: unknown = await response.json().catch(() => null)
  const segments: unknown =
    typeof body === 'object' && body !== null && 'segments' in body ? body.segments : null
  if (!Array.isArray(segments) || !segments.every(isPreviewSegment)) {
    throw new Error('preview_invalid')
  }
  return segments
}
