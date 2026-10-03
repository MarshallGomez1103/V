import { useEffect, useState } from 'react'

import { isAbortError } from '../api/errors'
import { getJobPreview, type PreviewSegment } from '../api/preview'

export const PREVIEW_INTERVAL_MS = 1500

export interface JobPreview {
  segments: PreviewSegment[]
  /** `false` si el backend no ofrece vista previa (la UI no la muestra). */
  available: boolean
}

interface Tracked extends JobPreview {
  jobId: string
}

const EMPTY: JobPreview = { segments: [], available: true }

const keyOf = (segment: PreviewSegment) =>
  String(segment.start_ms) + ':' + String(segment.end_ms) + ':' + segment.text

/**
 * Sondea los segmentos confirmados de un trabajo mientras `active` (TRANSCRIBING y aún
 * sin transcript). Acumula sin duplicar; pide solo lo posterior a lo ya recibido.
 */
export function useJobPreview(jobId: string | null, active: boolean): JobPreview {
  const [tracked, setTracked] = useState<Tracked | null>(null)

  useEffect(() => {
    if (jobId === null || !active) {
      return
    }
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    let after = 0
    const seen = new Set<string>()

    const apply = (batch: PreviewSegment[] | null) => {
      if (batch === null) {
        setTracked((current) => ({
          segments: current?.jobId === jobId ? current.segments : [],
          available: false,
          jobId,
        }))
        return
      }
      const fresh = batch.filter((segment) => !seen.has(keyOf(segment)))
      fresh.forEach((segment) => {
        seen.add(keyOf(segment))
        after = Math.max(after, segment.start_ms)
      })
      setTracked((current) => ({
        segments: [...(current?.jobId === jobId ? current.segments : []), ...fresh],
        available: true,
        jobId,
      }))
    }

    const poll = () => {
      getJobPreview(jobId, after, controller.signal)
        .then((batch) => {
          apply(batch)
          // Sin vista previa en el backend no se insiste.
          if (batch !== null) {
            timer = setTimeout(poll, PREVIEW_INTERVAL_MS)
          }
        })
        .catch((error: unknown) => {
          if (!isAbortError(error)) {
            timer = setTimeout(poll, PREVIEW_INTERVAL_MS * 2)
          }
        })
    }
    poll()

    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [jobId, active])

  return tracked !== null && tracked.jobId === jobId ? tracked : EMPTY
}
