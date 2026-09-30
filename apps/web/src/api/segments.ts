import { isAbortError, readErrorCode } from './errors'

// Tipo mínimo propio: no depende de TranscriptSegment.
export interface EditableSegment {
  id: string
  text: string
  revision: number
}

export class SegmentApiError extends Error {
  code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = 'SegmentApiError'
    this.code = code
  }
}

/** 409 segment_revision_conflict: lleva el segmento tal como está en el servidor. */
export class SegmentConflictError extends SegmentApiError {
  current: EditableSegment

  constructor(current: EditableSegment) {
    super(
      'segment_revision_conflict',
      messageForSegmentCode('segment_revision_conflict'),
    )
    this.name = 'SegmentConflictError'
    this.current = current
  }
}

const ERROR_MESSAGES: Record<string, string> = {
  segment_not_found: 'El segmento ya no existe.',
  segment_revision_conflict:
    'El segmento cambió en otro lugar mientras lo editabas.',
  segment_text_invalid: 'El texto del segmento no es válido.',
  network_error: 'No se pudo conectar con el servidor.',
  invalid_response: 'La API devolvió una respuesta inesperada.',
}

export function messageForSegmentCode(code: string): string {
  return (
    ERROR_MESSAGES[code] ??
    'No se pudo guardar el segmento (código ' + code + ').'
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function toEditable(value: unknown): EditableSegment | null {
  if (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.text === 'string' &&
    typeof value.revision === 'number'
  ) {
    return { id: value.id, text: value.text, revision: value.revision }
  }
  return null
}

async function errorFromResponse(response: Response): Promise<SegmentApiError> {
  const body: unknown = await response.json().catch(() => null)
  const code = readErrorCode(body)

  if (code === 'segment_revision_conflict') {
    const detail = isRecord(body) ? body.detail : null
    const current = isRecord(detail) ? toEditable(detail.current) : null
    if (current) {
      return new SegmentConflictError(current)
    }
    return new SegmentApiError(
      'invalid_response',
      messageForSegmentCode('invalid_response'),
    )
  }

  if (code) {
    return new SegmentApiError(code, messageForSegmentCode(code))
  }
  return new SegmentApiError(
    'http_' + response.status,
    'La API respondió con estado ' + response.status + '.',
  )
}

/** Guarda el texto de un segmento con concurrencia optimista por `revision`. */
export async function updateSegment(
  id: string,
  input: { text: string; revision: number },
  signal?: AbortSignal,
): Promise<EditableSegment> {
  let response: Response
  try {
    response = await fetch('/api/segments/' + encodeURIComponent(id), {
      method: 'PUT',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ text: input.text, revision: input.revision }),
      ...(signal ? { signal } : {}),
    })
  } catch (error) {
    if (isAbortError(error)) {
      throw error
    }
    throw new SegmentApiError(
      'network_error',
      messageForSegmentCode('network_error'),
    )
  }

  if (!response.ok) {
    throw await errorFromResponse(response)
  }

  const saved = toEditable(await response.json().catch(() => null))
  if (!saved) {
    throw new SegmentApiError(
      'invalid_response',
      messageForSegmentCode('invalid_response'),
    )
  }
  return saved
}
