import { useCallback, useEffect, useState } from 'react'

import { isAbortError } from '../api/errors'
import { listJobs, type JobView } from '../api/jobs'
import { listProjects, type Project } from '../api/projects'

export interface RecentJob {
  project: Project
  job: JobView
}

export type RecentJobsState =
  | { phase: 'loading' }
  | { phase: 'error'; message: string | null }
  | { phase: 'ready'; items: RecentJob[] }

const MAX_PROJECTS = 8
const MAX_ITEMS = 12

/**
 * Trabajos guardados en este equipo (más recientes primero). Sin esto, al recargar la
 * página una transcripción ya terminada no tendría cómo volver a abrirse.
 */
export function useRecentJobs(): RecentJobsState & { reload: () => void } {
  const [state, setState] = useState<RecentJobsState>({ phase: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      try {
        const projects = (await listProjects(controller.signal))
          .sort((a, b) => b.created_at.localeCompare(a.created_at))
          .slice(0, MAX_PROJECTS)
        const groups = await Promise.all(
          projects.map(async (project) =>
            (await listJobs(project.id, controller.signal)).map((job) => ({ project, job })),
          ),
        )
        const items = groups
          .flat()
          .sort((a, b) => b.job.created_at.localeCompare(a.job.created_at))
          .slice(0, MAX_ITEMS)
        setState({ phase: 'ready', items })
      } catch (error: unknown) {
        if (!isAbortError(error)) {
          setState({
            phase: 'error',
            message: error instanceof Error ? error.message : null,
          })
        }
      }
    })()
    return () => {
      controller.abort()
    }
  }, [attempt])

  const reload = useCallback(() => {
    setState({ phase: 'loading' })
    setAttempt((current) => current + 1)
  }, [])

  return { ...state, reload }
}
