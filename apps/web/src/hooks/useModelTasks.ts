import { useCallback, useEffect, useRef, useState } from 'react'

import { isAbortError } from '../api/errors'
import { listModelTasks, type TaskView } from '../api/models'

export const POLL_INTERVAL_MS = 1000

export function isActiveTask(task: TaskView): boolean {
  return task.state === 'queued' || task.state === 'running'
}

export interface ModelTasks {
  tasks: TaskView[]
  /** Último fallo de sondeo (null si el último sondeo funcionó). */
  error: string | null
  /** Registra una tarea recién creada para empezar a sondearla ya. */
  track: (task: TaskView) => void
  refresh: () => void
}

/**
 * Lista las tareas de instalación al montar y las sondea cada segundo solo mientras
 * haya alguna activa. `onCompleted` se dispara una vez por tarea vista activa que
 * pasa a `completed`.
 */
export function useModelTasks(onCompleted?: (task: TaskView) => void): ModelTasks {
  const [tasks, setTasks] = useState<TaskView[]>([])
  const [error, setError] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)
  const [settled, setSettled] = useState(0)
  const seen = useRef(new Map<string, TaskView['state']>())
  const onCompletedRef = useRef(onCompleted)

  useEffect(() => {
    onCompletedRef.current = onCompleted
  }, [onCompleted])

  const merge = useCallback((incoming: TaskView[]) => {
    for (const task of incoming) {
      const before = seen.current.get(task.id)
      seen.current.set(task.id, task.state)
      if (
        task.state === 'completed' &&
        (before === 'queued' || before === 'running')
      ) {
        onCompletedRef.current?.(task)
      }
    }
    setTasks(incoming)
  }, [])

  const track = useCallback((task: TaskView) => {
    seen.current.set(task.id, task.state)
    setTasks((current) => [task, ...current.filter((t) => t.id !== task.id)])
    // Relee la lista: descarta cualquier respuesta en vuelo que aún no incluía la tarea.
    setNonce((current) => current + 1)
  }, [])

  const refresh = useCallback(() => {
    setNonce((current) => current + 1)
  }, [])

  // Carga inicial y bajo demanda (nonce): una consulta completa de la lista.
  useEffect(() => {
    const controller = new AbortController()
    void listModelTasks(controller.signal)
      .then((incoming) => {
        merge(incoming)
        setError(null)
        setSettled((current) => current + 1)
      })
      .catch((failure: unknown) => {
        if (!isAbortError(failure)) {
          setError(
            failure instanceof Error
              ? failure.message
              : 'No se pudo consultar el estado de las tareas.',
          )
          setSettled((current) => current + 1)
        }
      })
    return () => {
      controller.abort()
    }
  }, [nonce, merge])

  // Sondeo: se agenda el siguiente solo cuando el anterior terminó (settled).
  const active = tasks.some(isActiveTask)
  useEffect(() => {
    if (!active) {
      return
    }
    const timer = setTimeout(() => {
      setNonce((current) => current + 1)
    }, POLL_INTERVAL_MS)
    return () => {
      clearTimeout(timer)
    }
  }, [active, settled])

  return { tasks, error, track, refresh }
}
