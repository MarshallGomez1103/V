import { useCallback, useEffect, useState } from 'react'

import { getHealth, type HealthPayload } from '../api/health'

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

  const isAvailable = state.phase === 'available'
  const statusLabel =
    state.phase === 'loading'
      ? 'Comprobando'
      : isAvailable
        ? 'Disponible'
        : 'Sin conexión'

  return (
    <article className="health-card" aria-labelledby="health-title">
      <div className="health-header">
        <div>
          <p className="section-kicker">SISTEMA</p>
          <h2 id="health-title">Listo para local</h2>
        </div>
        <span
          className={'status-light status-light--' + state.phase}
          aria-hidden="true"
        />
      </div>

      <div className="health-row" role="status" aria-live="polite">
        <div>
          <span className="health-label">API local</span>
          <span className="health-detail">127.0.0.1</span>
        </div>
        <strong>{statusLabel}</strong>
      </div>

      {isAvailable ? (
        <p className="health-message">
          El núcleo de VOZ respondió
          {state.payload.version ? ' · v' + state.payload.version : ''}.
        </p>
      ) : state.phase === 'unavailable' ? (
        <div className="health-error">
          <p>Inicia el servidor local para conectar la interfaz.</p>
          <button type="button" onClick={retry}>
            Volver a comprobar
          </button>
        </div>
      ) : (
        <p className="health-message">Verificando el servidor de este equipo…</p>
      )}
    </article>
  )
}
