import type { MessageKey } from '../i18n/messages'

export type ExportFormat = 'txt' | 'markdown' | 'srt' | 'vtt' | 'json'

export interface ExportOptions {
  format: ExportFormat
  timestamps: boolean
  groupBySpeaker: boolean
}

export const EXPORT_FORMATS: readonly { id: ExportFormat; label: MessageKey }[] = [
  { id: 'txt', label: 'export.txt' },
  { id: 'markdown', label: 'export.markdown' },
  { id: 'srt', label: 'export.srt' },
  { id: 'vtt', label: 'export.vtt' },
  { id: 'json', label: 'export.json' },
]

/** Solo TXT y Markdown aceptan tiempos y agrupación; el backend rechaza el resto. */
export function supportsExportOptions(format: ExportFormat): boolean {
  return format === 'txt' || format === 'markdown'
}

/** URL relativa de descarga; el backend responde con `Content-Disposition: attachment`. */
export function exportDocumentUrl(transcriptId: string, options: ExportOptions): string {
  const params = new URLSearchParams({ format: options.format })
  if (supportsExportOptions(options.format)) {
    if (options.timestamps) {
      params.set('timestamps', 'true')
    }
    if (options.groupBySpeaker) {
      params.set('group_by_speaker', 'true')
    }
  }
  return (
    '/api/transcripts/' + encodeURIComponent(transcriptId) + '/export?' + params.toString()
  )
}

export const PREVIEW_LINES = 14

/** Primeras líneas del documento que se descargaría con estas opciones (vista previa). */
export async function fetchExportPreview(
  url: string,
  signal?: AbortSignal,
): Promise<{ text: string; truncated: boolean }> {
  // ponytail: se pide el documento entero y se recorta aquí; el backend no pagina.
  const response = await fetch(url, signal ? { signal } : {})
  if (!response.ok) {
    throw new Error('export_preview_' + String(response.status))
  }
  const lines = (await response.text()).split('\n')
  const shown = lines.slice(0, PREVIEW_LINES)
  const text = shown.map((line) => (line.length > 160 ? line.slice(0, 160) + '…' : line)).join('\n')
  return { text, truncated: lines.length > PREVIEW_LINES }
}

/** Descarga directa: el servidor fija nombre y tipo con `Content-Disposition`. */
export function downloadFrom(href: string): void {
  const link = document.createElement('a')
  link.href = href
  link.download = ''
  document.body.append(link)
  link.click()
  link.remove()
}
