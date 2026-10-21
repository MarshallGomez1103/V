import { useCallback, useEffect, useState } from 'react'
import { Checkmark } from '@carbon/icons-react'
import { ActionableNotification } from '@carbon/react'

import { getHealth } from '../api/health'
import { useI18n } from '../i18n/i18n'
import { Busy } from './Busy'
import './HealthStatus.scss'

type CheckState =
  | { phase: 'loading' }
  | { phase: 'available' }
  | { phase: 'unavailable' }

export function HealthStatus() {
  const { t } = useI18n()
  const [state, setState] = useState<CheckState>({ phase: 'loading' })
  const [attempt, setAttempt] = useState(0)

  const retry = useCallback(() => {
    setState({ phase: 'loading' })
    setAttempt((current) => current + 1)
  }, [])

  useEffect(() => {
    const controller = new AbortController()

    void getHealth(controller.signal)
      .then(() => {
        setState({ phase: 'available' })
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setState({ phase: 'unavailable' })
        }
      })

    return () => {
      controller.abort()
    }
  }, [attempt])

  if (state.phase === 'unavailable') {
    return (
      <ActionableNotification
        kind="error"
        lowContrast
        inline
        hideCloseButton
        hasFocus={false}
        role="alert"
        title={t('health.offline.title')}
        subtitle={t('health.offline.subtitle')}
        actionButtonLabel={t('health.retry')}
        onActionButtonClick={retry}
      />
    )
  }

  return (
    <div className="voz-health" role="status" aria-live="polite">
      {state.phase === 'loading' ? (
        <Busy description={t('health.checking')} />
      ) : (
        <>
          <Checkmark size={16} aria-hidden="true" />
          <span>{t('health.ok')}</span>
        </>
      )}
    </div>
  )
}
