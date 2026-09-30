import { parseErrorCode } from './errors'

/** S5.09: peaks precalculados por el backend, `[min, max]` por bucket en [-1, 1]. */
export interface WaveformPeaks {
  media_asset_id: string
  duration_ms: number
  buckets: number
  peaks: [number, number][]
}

export class WaveformApiError extends Error {
  readonly code: string

  constructor(code: string) {
    super(describeWaveformError(code))
    this.name = 'WaveformApiError'
    this.code = code
  }
}

const WAVEFORM_MESSAGES: Record<string, string> = {
  media_asset_not_found: 'La grabación ya no existe.',
  peaks_buckets_invalid: 'La resolución de la forma de onda no es válida.',
  waveform_unavailable: 'No se pudo calcular la forma de onda de este audio.',
  invalid_response: 'La API devolvió una forma de onda inválida.',
  network_error: 'No se pudo conectar con el servidor local.',
}

export function describeWaveformError(code: string): string {
  return WAVEFORM_MESSAGES[code] ?? 'No se pudo cargar la forma de onda.'
}

function isPeakPair(value: unknown): value is [number, number] {
  return (
    Array.isArray(value) &&
    value.length === 2 &&
    typeof value[0] === 'number' &&
    typeof value[1] === 'number'
  )
}

function isWaveformPeaks(value: unknown): value is WaveformPeaks {
  return (
    typeof value === 'object' &&
    value !== null &&
    'media_asset_id' in value &&
    typeof value.media_asset_id === 'string' &&
    'duration_ms' in value &&
    typeof value.duration_ms === 'number' &&
    value.duration_ms > 0 &&
    'buckets' in value &&
    typeof value.buckets === 'number' &&
    'peaks' in value &&
    Array.isArray(value.peaks) &&
    value.peaks.length > 0 &&
    value.peaks.every(isPeakPair)
  )
}

export interface GetPeaksOptions {
  buckets?: number
  signal?: AbortSignal
}

export async function getWaveformPeaks(
  mediaAssetId: string,
  options: GetPeaksOptions = {},
): Promise<WaveformPeaks> {
  const { buckets, signal } = options
  const query = buckets === undefined ? '' : '?buckets=' + String(buckets)
  const url =
    '/api/media/' + encodeURIComponent(mediaAssetId) + '/peaks' + query

  let response: Response
  try {
    response = await fetch(url, signal ? { signal } : {})
  } catch (error) {
    if (signal?.aborted) {
      throw error
    }
    throw new WaveformApiError('network_error')
  }

  if (!response.ok) {
    const body = await response.text().catch(() => '')
    throw new WaveformApiError(
      parseErrorCode(body) ?? 'http_' + String(response.status),
    )
  }

  const body: unknown = await response.json().catch(() => null)
  if (!isWaveformPeaks(body)) {
    throw new WaveformApiError('invalid_response')
  }
  return body
}
