import { useState } from 'react'
import {
  MenuButton,
  MenuItem,
  MenuItemDivider,
  MenuItemGroup,
  MenuItemSelectable,
} from '@carbon/react'
import { Download } from '@carbon/icons-react'

import {
  EXPORT_FORMATS,
  exportDocumentUrl,
  type ExportFormat,
} from '../api/exportDocument'

export interface ExportMenuProps {
  transcriptId: string
}

/** Descarga directa: el servidor fija nombre y tipo con `Content-Disposition`. */
function download(href: string): void {
  const link = document.createElement('a')
  link.href = href
  link.download = ''
  document.body.append(link)
  link.click()
  link.remove()
}

// S10.14: el navegador descarga directamente; las opciones de tiempos y de
// agrupación solo las aplican TXT y Markdown (lo decide `exportDocumentUrl`).
export function ExportMenu({ transcriptId }: ExportMenuProps) {
  const [timestamps, setTimestamps] = useState(false)
  const [groupBySpeaker, setGroupBySpeaker] = useState(false)

  const exportAs = (format: ExportFormat) => {
    download(exportDocumentUrl(transcriptId, { format, timestamps, groupBySpeaker }))
  }

  return (
    <MenuButton label="Exportar" kind="tertiary" size="md" menuAlignment="bottom-end">
      <MenuItemSelectable
        label="Incluir tiempos (TXT y Markdown)"
        selected={timestamps}
        onChange={setTimestamps}
      />
      <MenuItemSelectable
        label="Agrupar por hablante (TXT y Markdown)"
        selected={groupBySpeaker}
        onChange={setGroupBySpeaker}
      />
      <MenuItemDivider />
      <MenuItemGroup label="Descargar como">
        {EXPORT_FORMATS.map((item) => (
          <MenuItem
            key={item.id}
            label={item.label}
            renderIcon={Download}
            onClick={() => {
              exportAs(item.id)
            }}
          />
        ))}
      </MenuItemGroup>
    </MenuButton>
  )
}
