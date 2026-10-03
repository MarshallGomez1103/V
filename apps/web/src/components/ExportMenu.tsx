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
import { useI18n } from '../i18n/i18n'

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
  const { t } = useI18n()
  const [timestamps, setTimestamps] = useState(false)
  const [groupBySpeaker, setGroupBySpeaker] = useState(false)

  const exportAs = (format: ExportFormat) => {
    download(exportDocumentUrl(transcriptId, { format, timestamps, groupBySpeaker }))
  }

  return (
    <MenuButton label={t('export.label')} kind="tertiary" size="md" menuAlignment="bottom-end">
      <MenuItemSelectable
        label={t('export.timestamps')}
        selected={timestamps}
        onChange={setTimestamps}
      />
      <MenuItemSelectable
        label={t('export.group')}
        selected={groupBySpeaker}
        onChange={setGroupBySpeaker}
      />
      <MenuItemDivider />
      <MenuItemGroup label={t('export.downloadAs')}>
        {EXPORT_FORMATS.map((item) => (
          <MenuItem
            key={item.id}
            label={t(item.label)}
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
