import { useCallback, useEffect, useState } from 'react'

import { getSynthesis, subscribeSynthesisEvents, type SynthesisView } from '../api/synthesis'

export interface SynthesisEventsState {
  job: SynthesisView | null
  ended: boolean
  /** Mensaje ya traducido de un fallo del stream (no del trabajo, que trae su `error_code`). */
  error: string | null
}

export interface SynthesisEvents extends SynthesisEventsState {
  /** Vuelve a abrir el stream tras perder la conexión. */
  retry: () => void
}

const IDLE: SynthesisEventsState = { job: null, ended: false, error: null }

type Tracked = SynthesisEventsState & { key: string }

/**
 * Sigue por SSE el progreso de una síntesis (mismo patrón que `useJobEvents`): una
 * instantánea HTTP inmediata, el stream hasta `end`, y cierre al cambiar de id o
 * desmontar. El estado lleva la clave del trabajo para no mostrar uno anterior.
 */
export function useSynthesisEvents(id: string | null): SynthesisEvents {
  const [tracked, setTracked] = useState<Tracked | null>(null)
  const [attempt, setAttempt] = useState(0)
  const retry = useCallback(() => {
    setAttempt((current) => current + 1)
  }, [])

  useEffect(() => {
    if (id === null) {
      return
    }
    const key = id
    const patch = (changes: Partial<SynthesisEventsState>) => {
      setTracked((current) => ({
        ...(current?.key === key ? current : IDLE),
        ...changes,
        key,
      }))
    }
    const controller = new AbortController()
    void getSynthesis(id, controller.signal)
      .then((job) => {
        setTracked((current) =>
          current?.key === key && current.job !== null
            ? current
            : { ...(current?.key === key ? current : IDLE), job, key },
        )
      })
      .catch(() => undefined)
    const stop = subscribeSynthesisEvents(id, {
      onJob: (job) => {
        patch({ job, error: null })
      },
      onEnd: () => {
        patch({ ended: true })
      },
      onError: (error) => {
        patch({ error: error.message })
      },
    })
    return () => {
      controller.abort()
      stop()
    }
  }, [id, attempt])

  if (id === null || tracked === null || tracked.key !== id) {
    return { ...IDLE, retry }
  }
  const { job, ended, error } = tracked
  return { job, ended, error, retry }
}
