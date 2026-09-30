import { isAbortError, readErrorCode } from './errors'

export interface Speaker {
  id: string
  name: string
  color: string
  segment_count: number
}

export class SpeakerApiError extends Error {
  code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = 'SpeakerApiError'
    this.code = code
  }
}

const ERROR_MESSAGES: Record<string, string> = {
  transcript_not_found: 'La transcripción ya no existe.',
  speaker_not_found: 'El hablante ya no existe.',
  speaker_update_invalid:
    'El nombre debe tener de 1 a 80 caracteres y el color ser #rrggbb.',
  speaker_merge_invalid:
    'Solo se pueden fusionar dos hablantes distintos de la misma transcripción.',
  segment_not_found: 'El segmento ya no existe.',
  segment_speaker_invalid:
    'Ese hablante no pertenece a la transcripción del segmento.',
  network_error: 'No se pudo conectar con el servidor.',
  invalid_response: 'La API devolvió una respuesta inesperada.',
}

export function messageForSpeakerCode(code: string): string {
  return (
    ERROR_MESSAGES[code] ?? 'No se pudo completar la acción (código ' + code + ').'
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function toSpeaker(value: unknown): Speaker | null {
  if (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.name === 'string' &&
    typeof value.color === 'string' &&
    typeof value.segment_count === 'number'
  ) {
    return {
      id: value.id,
      name: value.name,
      color: value.color,
      segment_count: value.segment_count,
    }
  }
  return null
}

function invalidResponse(): SpeakerApiError {
  return new SpeakerApiError(
    'invalid_response',
    messageForSpeakerCode('invalid_response'),
  )
}

async function request(
  url: string,
  method: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(url, {
      method,
      headers: {
        Accept: 'application/json',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      ...(signal ? { signal } : {}),
    })
  } catch (error) {
    if (isAbortError(error)) {
      throw error
    }
    throw new SpeakerApiError(
      'network_error',
      messageForSpeakerCode('network_error'),
    )
  }

  const payload: unknown = await response.json().catch(() => null)
  if (response.ok) {
    return payload
  }
  const code = readErrorCode(payload)
  throw code
    ? new SpeakerApiError(code, messageForSpeakerCode(code))
    : new SpeakerApiError(
        'http_' + response.status,
        'La API respondió con estado ' + response.status + '.',
      )
}

/** Hablantes que aparecen en una transcripción, con su número de segmentos. */
export async function listSpeakers(
  transcriptId: string,
  signal?: AbortSignal,
): Promise<Speaker[]> {
  const payload = await request(
    '/api/transcripts/' + encodeURIComponent(transcriptId) + '/speakers',
    'GET',
    undefined,
    signal,
  )
  const items: unknown = isRecord(payload) ? payload.speakers : null
  if (!Array.isArray(items)) {
    throw invalidResponse()
  }
  const speakers = items.map(toSpeaker)
  if (speakers.some((speaker) => speaker === null)) {
    throw invalidResponse()
  }
  return speakers as Speaker[]
}

/** Renombra y/o recolorea un hablante (no reejecuta ningún modelo). */
export async function updateSpeaker(
  id: string,
  changes: { name?: string; color?: string },
  signal?: AbortSignal,
): Promise<Speaker> {
  const speaker = toSpeaker(
    await request(
      '/api/speakers/' + encodeURIComponent(id),
      'PATCH',
      changes,
      signal,
    ),
  )
  if (!speaker) {
    throw invalidResponse()
  }
  return speaker
}

/** Fusiona `id` dentro de `into`: sus segmentos pasan al destino y el origen se borra. */
export async function mergeSpeakers(
  id: string,
  into: string,
  signal?: AbortSignal,
): Promise<Speaker> {
  const payload = await request(
    '/api/speakers/' + encodeURIComponent(id) + '/merge',
    'POST',
    { into },
    signal,
  )
  const speaker = toSpeaker(isRecord(payload) ? payload.speaker : null)
  if (!speaker) {
    throw invalidResponse()
  }
  return speaker
}

/** Reasigna a mano el hablante de un segmento (`null` lo deja sin hablante). */
export async function assignSegmentSpeaker(
  segmentId: string,
  speakerId: string | null,
  signal?: AbortSignal,
): Promise<void> {
  const payload = await request(
    '/api/segments/' + encodeURIComponent(segmentId) + '/speaker',
    'PUT',
    { speaker_id: speakerId },
    signal,
  )
  if (!isRecord(payload) || typeof payload.id !== 'string') {
    throw invalidResponse()
  }
}
