import { parseErrorCode } from './errors'

export interface MediaAssetSummary {
  media_asset_id: string
  project_id: string
  filename: string
  media_type: string | null
  duration_ms: number | null
  sha256: string
}

export class UploadError extends Error {
  readonly code: string

  constructor(code: string, message: string = describeUploadError(code)) {
    super(message)
    this.name = 'UploadError'
    this.code = code
  }
}

const UPLOAD_MESSAGES: Record<string, string> = {
  filename_invalid: 'El nombre del archivo no es válido.',
  project_not_found: 'El proyecto ya no existe.',
  media_too_large: 'El archivo supera el tamaño permitido.',
  media_unsupported: 'FFmpeg no reconoce este archivo como audio o video.',
  media_corrupt: 'El archivo parece dañado o incompleto.',
  media_storage_unavailable: 'No hay espacio o acceso al almacenamiento local.',
  media_import_failed: 'La importación falló en el servidor local.',
  network_error: 'No se pudo conectar con el servidor local.',
  aborted: 'La importación fue cancelada.',
}

export function describeUploadError(code: string): string {
  return UPLOAD_MESSAGES[code] ?? 'No se pudo importar el archivo.'
}

export interface UploadOptions {
  onProgress?: (fraction: number) => void
  signal?: AbortSignal
}

function isMediaAssetSummary(value: unknown): value is MediaAssetSummary {
  return (
    typeof value === 'object' &&
    value !== null &&
    'media_asset_id' in value &&
    typeof value.media_asset_id === 'string' &&
    'project_id' in value &&
    typeof value.project_id === 'string' &&
    'filename' in value &&
    typeof value.filename === 'string' &&
    'media_type' in value &&
    (typeof value.media_type === 'string' || value.media_type === null) &&
    'duration_ms' in value &&
    (typeof value.duration_ms === 'number' || value.duration_ms === null) &&
    'sha256' in value &&
    typeof value.sha256 === 'string'
  )
}

export function uploadMedia(
  projectId: string,
  file: File,
  options: UploadOptions = {},
): Promise<MediaAssetSummary> {
  const { onProgress, signal } = options

  return new Promise<MediaAssetSummary>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new UploadError('aborted'))
      return
    }

    const request = new XMLHttpRequest()
    const abort = () => {
      request.abort()
    }

    request.open('POST', '/api/projects/' + encodeURIComponent(projectId) + '/media')
    request.setRequestHeader('Accept', 'application/json')
    request.setRequestHeader('Content-Type', 'application/octet-stream')
    request.setRequestHeader('X-Voz-Filename', encodeURIComponent(file.name))

    request.upload.onprogress = (event: ProgressEvent) => {
      if (onProgress && event.lengthComputable && event.total > 0) {
        onProgress(Math.min(1, event.loaded / event.total))
      }
    }

    request.onload = () => {
      signal?.removeEventListener('abort', abort)

      if (request.status === 201 || request.status === 200) {
        let body: unknown
        try {
          body = JSON.parse(request.responseText)
        } catch {
          body = undefined
        }

        if (isMediaAssetSummary(body)) {
          onProgress?.(1)
          resolve(body)
        } else {
          reject(
            new UploadError('invalid_response', 'La API devolvió un archivo inválido.'),
          )
        }
        return
      }

      const code = parseErrorCode(request.responseText) ?? 'http_' + request.status
      reject(new UploadError(code))
    }

    request.onerror = () => {
      signal?.removeEventListener('abort', abort)
      reject(new UploadError('network_error'))
    }

    request.onabort = () => {
      signal?.removeEventListener('abort', abort)
      reject(new UploadError('aborted'))
    }

    signal?.addEventListener('abort', abort, { once: true })
    request.send(file)
  })
}
