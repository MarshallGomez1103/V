import { useState } from 'react'
import { createPortal } from 'react-dom'
import { HeaderGlobalAction, Modal } from '@carbon/react'
import { Power } from '@carbon/icons-react'

import { shutdownServer } from '../api/shutdown'
import { useI18n } from '../i18n/i18n'
import { Notice } from './Notice'

interface ShutdownActionProps {
  /** Hay una transcripción en curso: se avisa antes de cerrar. */
  jobActive: boolean
  /** El servidor aceptó apagarse (o ya no responde). */
  onClosed: () => void
}

/** Botón «Cerrar servidor» del header, con confirmación y aviso si hay un trabajo en curso. */
export function ShutdownAction({ jobActive, onClosed }: ShutdownActionProps) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)

  const close = () => {
    if (!busy) {
      setOpen(false)
      setFailed(false)
    }
  }

  const confirm = () => {
    setBusy(true)
    setFailed(false)
    shutdownServer()
      .then(onClosed)
      .catch(() => {
        setFailed(true)
        setBusy(false)
      })
  }

  return (
    <>
      <HeaderGlobalAction
        aria-label={t('shutdown.button')}
        tooltipAlignment="end"
        onClick={() => {
          setOpen(true)
        }}
      >
        <Power size={20} />
      </HeaderGlobalAction>
      {open
        ? createPortal(
            <Modal
              open
              danger
              size="sm"
              modalHeading={t('shutdown.title')}
              closeButtonLabel={t('common.close')}
              primaryButtonText={busy ? t('shutdown.closing') : t('shutdown.confirm')}
              secondaryButtonText={t('shutdown.cancel')}
              primaryButtonDisabled={busy}
              onRequestClose={close}
              onRequestSubmit={confirm}
            >
              <p>{t('shutdown.body')}</p>
              {jobActive ? (
                <Notice kind="warning" role="alert" title={t('shutdown.activeJob')} />
              ) : null}
              {failed ? (
                <Notice kind="error" role="alert" title={t('shutdown.failed')} />
              ) : null}
            </Modal>,
            document.body,
          )
        : null}
    </>
  )
}
