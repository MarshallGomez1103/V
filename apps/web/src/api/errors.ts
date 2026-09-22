export interface ApiErrorDetail {
  code: string
  message: string
}

/** Extrae `detail.code` de un cuerpo de error del backend, si tiene la forma esperada. */
export function readErrorCode(body: unknown): string | undefined {
  if (typeof body !== 'object' || body === null || !('detail' in body)) {
    return undefined
  }

  const detail: unknown = body.detail

  if (
    typeof detail === 'object' &&
    detail !== null &&
    'code' in detail &&
    typeof detail.code === 'string'
  ) {
    return detail.code
  }

  return undefined
}

export function parseErrorCode(responseText: string): string | undefined {
  try {
    return readErrorCode(JSON.parse(responseText))
  } catch {
    return undefined
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}
