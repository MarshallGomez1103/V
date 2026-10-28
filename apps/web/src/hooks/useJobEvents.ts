import { useEffect, useState } from 'react'

import { subscribeJobEvents, type JobView } from '../api/jobEvents'
import { getJob, JobApiError, messageForFailure } from '../api/jobs'
import { isAbortError } from '../api/errors'

export interface JobEventsState {
  job: JobView | null
  ended: boolean
  error: string | null
  /** El servidor dijo que el trabajo no existe: reintentar no sirve. */
  notFound?: true
}

const IDLE: JobEventsState = { job: null, ended: false, error: null }

type Tracked = JobEventsState & { jobId: string; attempt: number }

/**
 * Follow one job's SSE stream; resubscribes when `jobId` changes and closes
 * the stream on unmount. State is tagged with its job id so a stale snapshot
 * from a previous id is never shown for the current one. Cambiar `attempt`
 * vuelve a pedir la instantánea y reabre el stream (reintento tras un fallo).
 */
export function useJobEvents(jobId: string | null, attempt = 0): JobEventsState {
  const [tracked, setTracked] = useState<Tracked | null>(null)

  useEffect(() => {
    if (jobId === null) {
      return
    }
    const patch = (changes: Partial<JobEventsState>) => {
      setTracked((current) => ({
        ...(current?.jobId === jobId ? current : IDLE),
        ...changes,
        jobId,
        attempt,
      }))
    }
    // Instantánea inmediata por HTTP: si el stream tarda o falla (p. ej. al reabrir un
    // trabajo guardado) la pantalla igual muestra el estado del trabajo.
    const controller = new AbortController()
    let notFound = false
    void getJob(jobId, controller.signal)
      .then((job) => {
        setTracked((current) =>
          current?.jobId === jobId && current.job !== null
            ? current
            : { ...(current?.jobId === jobId ? current : IDLE), job, error: null, jobId, attempt },
        )
      })
      .catch((failure: unknown) => {
        if (isAbortError(failure)) {
          return
        }
        // Un fallo de la instantánea solo se muestra si el stream aún no trajo el trabajo.
        const message = messageForFailure(failure)
        notFound = failure instanceof JobApiError && failure.code === 'job_not_found'
        setTracked((current) =>
          current?.jobId === jobId && current.job !== null
            ? current
            : {
                ...(current?.jobId === jobId ? current : IDLE),
                error: message,
                ...(notFound ? { notFound: true as const } : {}),
                jobId,
                attempt,
              },
        )
      })
    const stop = subscribeJobEvents(jobId, {
      onJob: (job) => patch({ job, error: null }),
      onEnd: () => patch({ ended: true }),
      onError: (error) => {
        // Si la instantánea ya dijo que no existe, ese mensaje es el útil.
        if (!notFound) {
          patch({ error: error.message })
        }
      },
    })
    return () => {
      controller.abort()
      stop()
    }
  }, [jobId, attempt])

  if (jobId === null || tracked === null || tracked.jobId !== jobId) {
    return IDLE
  }
  const { job, ended, error, notFound } = tracked
  // Tras reintentar, el error anterior se oculta mientras llega la respuesta nueva.
  if (tracked.attempt !== attempt) {
    return { job, ended, error: null }
  }
  return { job, ended, error, ...(notFound ? { notFound } : {}) }
}
