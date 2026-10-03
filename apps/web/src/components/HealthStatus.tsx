import { useCallback, useEffect, useState } from 'react'
import { ActionableNotification, Tag } from '@carbon/react'

import { getHealth, type HealthPayload } from '../api/health'
import { Busy } from './Busy'
import './HealthStatus.scss'

type CheckState =
  | { phase: 'loading' }
  | { phase: 'available'; payload: HealthPayload }
  | { phase: 'unavailable' }

export function HealthStatus() {
  const [state, setState] = useState<CheckState>({ phase: 'loading' })
  const [attempt, setAttempt] = useState(0)

  const retry = useCallback(() => {
    setState({ phase: 'loading' })
    setAttempt((current) => current + 1)
  }, [])

  useEffect(() => {
    const controller = new AbortController()

    void getHealth(controller.signal)
      .then((payload) => {
        setState({ phase: 'available', payload })
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
        title="Sin conexión"
        subtitle="Inicia el servidor local para conectar la interfaz."
        actionButtonLabel="Volver a comprobar"
        onActionButtonClick={retry}
      />
    )
  }

  return (
    <div className="voz-health" role="status" aria-live="polite">
      {state.phase === 'loading' ? (
        <Busy description="Comprobando el servidor de este equipo…" />
      ) : (
        <>
          <Tag type="green" size="sm">
            Disponible
          </Tag>
          <span>
            API local · 127.0.0.1
            {state.payload.version ? ' · v' + state.payload.version : ''}
          </span>
        </>
      )}
    </div>
  )
}
