import { useCallback, useEffect, useState } from 'react'

import { isAbortError } from '../api/errors'
import {
  cancelModelTask,
  getModels,
  installModel,
  messageForModelError,
  ModelApiError,
  type ModelView,
  type TaskView,
} from '../api/models'
import { isActiveTask, useModelTasks } from './useModelTasks'

export type DiarizationModelStatus =
  /** Hablantes desactivados: no se consulta nada. */
  | 'off'
  | 'checking'
  | 'ready'
  | 'missing'
  | 'downloading'
  /** Falta el extra de Python que ejecuta el modelo: descargarlo no serviría. */
  | 'unavailable'
  | 'error'

export interface DiarizationModelState {
  status: DiarizationModelStatus
  model: ModelView | null
  task: TaskView | null
  /** Mensaje de la última descarga fallida o de la consulta que falló. */
  error: string | null
  /** Pide la descarga (el botón con el tamaño ya es el consentimiento). */
  download: () => void
  cancel: () => void
  retry: () => void
}

type Loaded =
  | { key: number; phase: 'ready'; model: ModelView | null }
  | { key: number; phase: 'error'; message: string }

/**
 * Estado del modelo de hablantes (`diarization:*` en `/api/models`) mientras el
 * interruptor «Detectar quién habla» está activo: si falta, ofrece descargarlo en
 * línea y expone el progreso para que la pantalla bloquee Transcribir hasta tenerlo.
 */
export function useDiarizationModel(
  enabled: boolean,
  refreshKey = 0,
): DiarizationModelState {
  const [version, setVersion] = useState(0)
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [startError, setStartError] = useState<string | null>(null)
  const query = version * 1_000_000 + refreshKey

  const onCompleted = useCallback(() => {
    setVersion((current) => current + 1)
  }, [])
  const { tasks, track, refresh } = useModelTasks(onCompleted)

  useEffect(() => {
    if (!enabled) {
      return
    }
    const controller = new AbortController()
    getModels(controller.signal)
      .then((payload) => {
        setLoaded({
          key: query,
          phase: 'ready',
          model: payload.models.find((model) => model.kind === 'diarization') ?? null,
        })
      })
      .catch((failure: unknown) => {
        if (!isAbortError(failure)) {
          setLoaded({
            key: query,
            phase: 'error',
            message:
              failure instanceof ModelApiError
                ? failure.message
                : messageForModelError('network_error'),
          })
        }
      })
    return () => {
      controller.abort()
    }
  }, [enabled, query])

  const model = loaded?.phase === 'ready' ? loaded.model : null
  const active =
    model === null
      ? null
      : (tasks
          .filter((task) => task.key === model.key && isActiveTask(task))
          .sort((a, b) => b.created_at.localeCompare(a.created_at))[0] ?? null)
  const latest =
    model === null
      ? null
      : (tasks
          .filter((task) => task.key === model.key)
          .sort((a, b) => b.created_at.localeCompare(a.created_at))[0] ?? null)

  const download = useCallback(() => {
    if (model === null) {
      return
    }
    setStartError(null)
    installModel(model.key, 'download')
      .then(track)
      .catch((failure: unknown) => {
        setStartError(
          failure instanceof ModelApiError
            ? failure.message
            : messageForModelError('network_error'),
        )
        setVersion((current) => current + 1)
      })
  }, [model, track])

  const cancel = useCallback(() => {
    if (active === null) {
      return
    }
    cancelModelTask(active.id)
      .catch(() => undefined)
      .finally(refresh)
  }, [active, refresh])

  const retry = useCallback(() => {
    setStartError(null)
    setLoaded(null)
    setVersion((current) => current + 1)
  }, [])

  let status: DiarizationModelStatus
  if (!enabled) {
    status = 'off'
  } else if (model !== null && !model.installed && active !== null) {
    status = 'downloading'
  } else if (loaded === null || loaded.key !== query) {
    status = 'checking'
  } else if (loaded.phase === 'error') {
    status = 'error'
  } else if (model === null) {
    status = 'unavailable'
  } else if (model.installed) {
    status = 'ready'
  } else {
    status = model.runtime_available ? 'missing' : 'unavailable'
  }

  const failedTask = latest !== null && latest.state === 'failed' ? latest : null
  const error =
    startError ??
    (loaded?.phase === 'error' ? loaded.message : null) ??
    (failedTask !== null && status === 'missing'
      ? messageForModelError(failedTask.error_code ?? 'model_task_failed')
      : null)

  return {
    status,
    model,
    task: active ?? latest,
    error,
    download,
    cancel,
    retry,
  }
}
