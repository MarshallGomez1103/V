import { useState } from 'react'

import {
  EXPORT_FORMATS,
  exportDocumentUrl,
  supportsExportOptions,
  type ExportFormat,
} from '../api/exportDocument'
import './ExportMenu.css'

export interface ExportMenuProps {
  transcriptId: string
}

// S10.14: el navegador descarga directamente; el servidor fija nombre y tipo.
export function ExportMenu({ transcriptId }: ExportMenuProps) {
  const [format, setFormat] = useState<ExportFormat>('txt')
  const [timestamps, setTimestamps] = useState(false)
  const [groupBySpeaker, setGroupBySpeaker] = useState(false)
  const optionsEnabled = supportsExportOptions(format)
  const href = exportDocumentUrl(transcriptId, { format, timestamps, groupBySpeaker })

  return (
    <div className="export-menu" role="group" aria-label="Exportar transcripción">
      <label className="export-menu-field">
        Formato
        <select
          value={format}
          onChange={(event) => {
            setFormat(event.target.value as ExportFormat)
          }}
        >
          {EXPORT_FORMATS.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <label className="export-menu-field">
        <input
          type="checkbox"
          checked={optionsEnabled && timestamps}
          disabled={!optionsEnabled}
          onChange={(event) => {
            setTimestamps(event.target.checked)
          }}
        />
        Incluir tiempos
      </label>
      <label className="export-menu-field">
        <input
          type="checkbox"
          checked={optionsEnabled && groupBySpeaker}
          disabled={!optionsEnabled}
          onChange={(event) => {
            setGroupBySpeaker(event.target.checked)
          }}
        />
        Agrupar por speaker
      </label>
      <a className="export-menu-download" href={href} download>
        Descargar
      </a>
    </div>
  )
}
