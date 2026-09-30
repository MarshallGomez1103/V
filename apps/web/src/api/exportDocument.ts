export type ExportFormat = 'txt' | 'markdown' | 'srt' | 'vtt' | 'json'

export interface ExportOptions {
  format: ExportFormat
  timestamps: boolean
  groupBySpeaker: boolean
}

export const EXPORT_FORMATS: readonly { id: ExportFormat; label: string }[] = [
  { id: 'txt', label: 'Texto (.txt)' },
  { id: 'markdown', label: 'Markdown (.md)' },
  { id: 'srt', label: 'Subtítulos SRT (.srt)' },
  { id: 'vtt', label: 'Subtítulos WebVTT (.vtt)' },
  { id: 'json', label: 'JSON canónico (.json)' },
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
