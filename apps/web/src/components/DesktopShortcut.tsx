import { useEffect, useState } from 'react'
import { Button } from '@carbon/react'
import { Launch } from '@carbon/icons-react'

import { createShortcut, getShortcutStatus, type ShortcutStatus } from '../api/desktopShortcut'
import { useI18n } from '../i18n/i18n'

/**
 * «Crear icono en el escritorio» (o «Volver a crearlo»). Se oculta si el sistema no lo
 * admite o el servidor no ofrece la función; consulta el estado solo al abrir el menú.
 */
export function DesktopShortcut({ active }: { active: boolean }) {
  const { t } = useI18n()
  const [status, setStatus] = useState<ShortcutStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [outcome, setOutcome] = useState<'created' | 'failed' | null>(null)

  useEffect(() => {
    if (!active) {
      return
    }
    const controller = new AbortController()
    getShortcutStatus(controller.signal)
      .then(setStatus)
      .catch(() => undefined)
    return () => {
      controller.abort()
    }
  }, [active])

  if (status === null || !status.supported) {
    return null
  }

  const create = () => {
    setBusy(true)
    setOutcome(null)
    createShortcut()
      .then((next) => {
        setStatus(next)
        setOutcome('created')
      })
      .catch(() => {
        setOutcome('failed')
      })
      .finally(() => {
        setBusy(false)
      })
  }

  return (
    <div className="voz-shortcut">
      <p className="voz-choices__legend">{t('shortcut.title')}</p>
      <div className="voz-shortcut__body">
        <Button kind="tertiary" size="sm" renderIcon={Launch} disabled={busy} onClick={create}>
          {status.exists ? t('shortcut.recreate') : t('shortcut.create')}
        </Button>
        <p className="voz-field-note" role="status">
          {outcome === 'created'
            ? t('shortcut.created')
            : outcome === 'failed'
              ? t('shortcut.failed')
              : status.exists
                ? t('shortcut.exists')
                : t('shortcut.help')}
        </p>
      </div>
    </div>
  )
}
