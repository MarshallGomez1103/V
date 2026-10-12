import { useEffect, useState } from 'react'
import { Button } from '@carbon/react'
import { Launch, TrashCan } from '@carbon/icons-react'

import {
  createShortcut,
  getShortcutStatus,
  removeShortcut,
  type ShortcutStatus,
} from '../api/desktopShortcut'
import { useI18n } from '../i18n/i18n'

type Outcome = 'created' | 'removed' | 'failed' | 'removeFailed' | null

/**
 * Acceso directo: crearlo, volver a crearlo (también cuando quedó roto) y quitarlo, con
 * confirmación en línea (un modal fuera del menú lo cerraría). Se oculta si el sistema no lo
 * admite y no hay ninguno que quitar, o si el servidor no ofrece la función; consulta el estado
 * solo al abrir el menú.
 */
export function DesktopShortcut({ active }: { active: boolean }) {
  const { t } = useI18n()
  const [status, setStatus] = useState<ShortcutStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [outcome, setOutcome] = useState<Outcome>(null)

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

  if (status === null || !(status.supported || status.exists || status.broken)) {
    return null
  }

  const present = status.exists || status.broken

  const run = (action: () => Promise<ShortcutStatus>, done: Outcome, failed: Outcome) => {
    setBusy(true)
    setConfirming(false)
    setOutcome(null)
    action()
      .then((next) => {
        setStatus(next)
        setOutcome(done)
      })
      .catch(() => {
        setOutcome(failed)
      })
      .finally(() => {
        setBusy(false)
      })
  }

  const note =
    outcome === 'created'
      ? t('shortcut.created')
      : outcome === 'removed'
        ? t('shortcut.removed')
        : outcome === 'failed'
          ? t('shortcut.failed')
          : outcome === 'removeFailed'
            ? t('shortcut.removeFailed')
            : status.broken
              ? t('shortcut.broken')
              : status.exists
                ? t('shortcut.exists')
                : t('shortcut.help')

  return (
    <div className="voz-shortcut">
      <p className="voz-choices__legend">{t('shortcut.title')}</p>
      <div className="voz-shortcut__body">
        {status.supported ? (
          <Button
            kind="tertiary"
            size="sm"
            renderIcon={Launch}
            disabled={busy}
            onClick={() => {
              run(createShortcut, 'created', 'failed')
            }}
          >
            {present ? t('shortcut.recreate') : t('shortcut.create')}
          </Button>
        ) : null}
        {present && !confirming ? (
          <Button
            kind="ghost"
            size="sm"
            renderIcon={TrashCan}
            disabled={busy}
            onClick={() => {
              setConfirming(true)
            }}
          >
            {t('shortcut.remove')}
          </Button>
        ) : null}
        {present && confirming ? (
          <div role="group" aria-label={t('shortcut.remove')} className="voz-shortcut__confirm">
            <p className="voz-field-note">{t('shortcut.removeConfirm')}</p>
            <div className="voz-shortcut__actions">
              <Button
                kind="danger"
                size="sm"
                disabled={busy}
                onClick={() => {
                  run(removeShortcut, 'removed', 'removeFailed')
                }}
              >
                {t('shortcut.removeYes')}
              </Button>
              <Button
                kind="ghost"
                size="sm"
                onClick={() => {
                  setConfirming(false)
                }}
              >
                {t('shortcut.cancel')}
              </Button>
            </div>
          </div>
        ) : null}
        <p
          className={
            status.broken && outcome === null
              ? 'voz-field-note voz-shortcut__broken'
              : 'voz-field-note'
          }
          role="status"
        >
          {note}
        </p>
      </div>
    </div>
  )
}
