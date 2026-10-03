import { useEffect, useState } from 'react'

import { subscribeJobEvents, type JobView } from '../api/jobEvents'
import { getJob } from '../api/jobs'

export interface JobEventsState {
  job: JobView | null
  ended: boolean
  error: string | null
}

const IDLE: JobEventsState = { job: null, ended: false, error: null }

type Tracked = JobEventsState & { jobId: string }

/**
 * Follow one job's SSE stream; resubscribes when `jobId` changes and closes
 * the stream on unmount. State is tagged with its job id so a stale snapshot
 * from a previous id is never shown for the current one.
 */
export function useJobEvents(jobId: string | null): JobEventsState {
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
      }))
    }
    // Instantánea inmediata por HTTP: si el stream tarda o falla (p. ej. al reabrir un
    // trabajo guardado) la pantalla igual muestra el estado del trabajo.
    const controller = new AbortController()
    void getJob(jobId, controller.signal)
      .then((job) => {
        setTracked((current) =>
          current?.jobId === jobId && current.job !== null
            ? current
            : { ...(current?.jobId === jobId ? current : IDLE), job, jobId },
        )
      })
      .catch(() => undefined)
    const stop = subscribeJobEvents(jobId, {
      onJob: (job) => patch({ job, error: null }),
      onEnd: () => patch({ ended: true }),
      onError: (error) => patch({ error: error.message }),
    })
    return () => {
      controller.abort()
      stop()
    }
  }, [jobId])

  if (jobId === null || tracked === null || tracked.jobId !== jobId) {
    return IDLE
  }
  const { job, ended, error } = tracked
  return { job, ended, error }
}
