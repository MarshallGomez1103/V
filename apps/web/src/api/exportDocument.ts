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
