import { useCallback, useEffect, useId, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'

import { isAbortError } from '../api/errors'
import {
  cancelModelTask,
  deleteModel,
  getModels,
  installModel,
  messageForModelError,
  ModelApiError,
  type InstallMethod,
  type ModelsPayload,
  type ModelView,
  type TaskView,
} from '../api/models'
import { isActiveTask, useModelTasks } from '../hooks/useModelTasks'
import { formatBytes } from '../lib/formatBytes'
import { compareModelIds } from '../lib/modelOrder'
import './ModelManager.css'

export interface ModelManagerProps {
  onModelsChanged?: () => void
}

type LoadState =
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; payload: ModelsPayload }

type DialogState =
  | { kind: 'download'; model: ModelView }
  | { kind: 'delete'; model: ModelView }

const PROFILE_LABELS: Record<string, string> = {
  fast: 'Rápido',
  quality: 'Calidad',
}

const RECOMMENDED_KEY = 'faster-whisper:turbo'

/** Runtime externo que cada familia necesita, en lenguaje del usuario. */
const REQUIRES_LABELS: Record<string, string> = {
  'whisper-cli': 'whisper-cli',
  diarization: 'el extra diarization',
}

function requiresLabel(requires: string): string {
  return Object.hasOwn(REQUIRES_LABELS, requires)
    ? (REQUIRES_LABELS[requires] ?? requires)
    : requires
}

/** faster-whisper primero, luego el resto de proveedores; dentro, orden de catálogo. */
function compareModels(a: ModelView, b: ModelView): number {
  const home = (m: ModelView) => (m.provider_id === 'faster-whisper' ? 0 : 1)
  return home(a) - home(b) || compareModelIds(a.model_id, b.model_id)
}

function errorMessage(error: unknown): string {
  return error instanceof ModelApiError
    ? error.message
    : 'No se pudo completar la operación. Inténtalo de nuevo.'
}

function taskPercent(task: TaskView): number | null {
  return task.total_bytes > 0
    ? Math.min(100, Math.floor((task.done_bytes / task.total_bytes) * 100))
    : null
}

function describeTask(task: TaskView): string {
  if (task.state === 'queued') {
    return 'En cola…'
  }
  const verb = task.method === 'import' ? 'Importando desde Buzz' : 'Descargando'
  const percent = taskPercent(task)
  return percent === null
    ? verb + '…'
    : verb +
        ': ' +
        String(percent) +
        ' % (' +
        formatBytes(task.done_bytes) +
        ' de ' +
        formatBytes(task.total_bytes) +
        ')'
}

/** Tarea más reciente de cada modelo, por clave (por fecha de creación ISO). */
function latestByModel(tasks: TaskView[]): Map<string, TaskView> {
  const latest = new Map<string, TaskView>()
  for (const task of tasks) {
    const current = latest.get(task.key)
    if (!current || task.created_at >= current.created_at) {
      latest.set(task.key, task)
    }
  }
  return latest
}

interface ModalDialogProps {
  title: string
  onClose: () => void
  children: ReactNode
}

/** `<dialog>` nativo modal: Escape cierra, el foco entra al abrir y vuelve al disparador. */
function ModalDialog({ title, onClose, children }: ModalDialogProps) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) {
      return
    }
    const opener = document.activeElement
    dialog.showModal()
    dialog.querySelector<HTMLElement>('[data-autofocus]')?.focus()
    return () => {
      dialog.close()
      // ponytail: si el disparador ya no existe (p. ej. pasó a mostrar progreso) el foco cae al body.
      if (opener instanceof HTMLElement && opener.isConnected) {
        opener.focus()
      }
    }
  }, [])

  return (
    <dialog
      ref={ref}
      className="model-dialog"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
    >
      <h3 id={titleId}>{title}</h3>
      {children}
    </dialog>
  )
}

function DownloadDialog({
  model,
  freeBytes,
  onConfirm,
  onClose,
}: {
  model: ModelView
  freeBytes: number | null
  onConfirm: () => void
  onClose: () => void
}) {
  const insufficient = freeBytes !== null && freeBytes < model.size_bytes
  return (
    <ModalDialog title={'Descargar ' + model.display_name} onClose={onClose}>
      <p>
        Se descargarán <strong>{formatBytes(model.size_bytes)}</strong> desde{' '}
        {model.kind === 'diarization' ? (
          <strong>GitHub</strong>
        ) : (
          <>
            <strong>HuggingFace</strong> ({model.source})
          </>
        )}
        . Es la única vez que VOZ necesita Internet para este modelo: después
        funciona sin conexión.
      </p>
      {insufficient ? (
        <p className="model-dialog-warning" role="alert">
          Solo quedan {formatBytes(freeBytes)} libres: la descarga probablemente
          falle por falta de espacio.
        </p>
      ) : null}
      <div className="model-dialog-actions">
        <button type="button" onClick={onClose}>
          Cancelar
        </button>
        <button
          type="button"
          className="model-primary"
          data-autofocus
          onClick={onConfirm}
        >
          Descargar
        </button>
      </div>
    </ModalDialog>
  )
}

function DeleteDialog({
  model,
  onDeleted,
  onClose,
}: {
  model: ModelView
  onDeleted: () => void
  onClose: () => void
}) {
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputId = useId()

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (typed !== model.model_id || busy) {
      return
    }
    setBusy(true)
    setError(null)
    deleteModel(model.key)
      .then(onDeleted)
      .catch((failure: unknown) => {
        setError(errorMessage(failure))
        setBusy(false)
      })
  }

  return (
    <ModalDialog title={'Eliminar ' + model.display_name} onClose={onClose}>
      <form onSubmit={submit}>
        <p>
          Se liberarán{' '}
          <strong>{formatBytes(model.disk_bytes ?? model.size_bytes)}</strong>{' '}
          de disco. Tus transcripciones se conservan, pero no podrás volver a
          usar este modelo hasta instalarlo otra vez.
        </p>
        <label htmlFor={inputId}>
          Para confirmar, escribe <code>{model.model_id}</code>
        </label>
        <input
          id={inputId}
          type="text"
          value={typed}
          autoComplete="off"
          spellCheck={false}
          data-autofocus
          onChange={(event) => {
            setTyped(event.target.value)
          }}
        />
        {error ? (
          <p className="model-dialog-warning" role="alert">
            {error}
          </p>
        ) : null}
        <div className="model-dialog-actions">
          <button type="button" onClick={onClose}>
            Cancelar
          </button>
          <button
            type="submit"
            className="model-danger"
            disabled={typed !== model.model_id || busy}
          >
            {busy ? 'Eliminando…' : 'Eliminar'}
          </button>
        </div>
      </form>
    </ModalDialog>
  )
}

interface ModelRowProps {
  model: ModelView
  task: TaskView | undefined
  notice: string | undefined
  busy: boolean
  onImport: () => void
  onDownload: () => void
  onDelete: () => void
  onCancel: (task: TaskView) => void
}

function ModelRow({
  model,
  task,
  notice,
  busy,
  onImport,
  onDownload,
  onDelete,
  onCancel,
}: ModelRowProps) {
  const titleId = useId()
  const helpId = useId()
  const hasBuzz = model.external.some((entry) => entry.origin === 'buzz')
  const missingRuntime = !model.runtime_available && model.requires !== null
  const active = task && isActiveTask(task) ? task : undefined
  const failure =
    !model.installed && task?.state === 'failed'
      ? messageForModelError(task.error_code ?? 'model_task_failed')
      : null
  const cancelled = !model.installed && task?.state === 'cancelled'
  const status = model.installed
    ? 'Instalado'
    : hasBuzz
      ? 'Disponible en Buzz'
      : 'No instalado'
  const percent = active ? taskPercent(active) : null

  return (
    <li
      className={'model-row' + (model.installed ? ' model-row--installed' : '')}
      aria-labelledby={titleId}
    >
      <div className="model-head">
        <h3 id={titleId}>{model.display_name}</h3>
        {model.key === RECOMMENDED_KEY ? (
          <span className="model-badge model-badge--recommended">
            Recomendado
          </span>
        ) : null}
        <span
          className={
            'model-badge' + (model.installed ? ' model-badge--installed' : '')
          }
        >
          {status}
        </span>
      </div>

      <dl className="model-meta">
        {model.profile !== null ? (
          <div>
            <dt>Perfil</dt>
            <dd>{PROFILE_LABELS[model.profile] ?? model.profile}</dd>
          </div>
        ) : null}
        <div>
          <dt>Tamaño</dt>
          <dd>{formatBytes(model.size_bytes)}</dd>
        </div>
        <div>
          <dt>Licencia</dt>
          <dd>{model.license}</dd>
        </div>
        {model.requires !== null ? (
          <div>
            <dt>Requiere</dt>
            <dd>{requiresLabel(model.requires)}</dd>
          </div>
        ) : null}
        {model.installed && model.disk_bytes !== null ? (
          <div>
            <dt>En disco</dt>
            <dd>{formatBytes(model.disk_bytes)}</dd>
          </div>
        ) : null}
      </dl>

      {active ? (
        <div className="model-progress" role="status">
          <progress
            aria-label={'Progreso de ' + model.display_name}
            max={active.total_bytes > 0 ? active.total_bytes : undefined}
            value={
              active.total_bytes > 0 && percent !== null
                ? active.done_bytes
                : undefined
            }
          />
          <span>{describeTask(active)}</span>
          <button
            type="button"
            onClick={() => {
              onCancel(active)
            }}
          >
            Cancelar
          </button>
        </div>
      ) : (
        <div className="model-actions">
          {!model.installed && !missingRuntime && hasBuzz ? (
            <>
              <button
                type="button"
                className="model-primary"
                disabled={busy}
                aria-describedby={helpId}
                onClick={onImport}
              >
                Importar desde Buzz
              </button>
              <p className="model-help" id={helpId}>
                Reutiliza los archivos que Buzz ya tiene en este equipo: no
                descarga nada y no los mueve ni los modifica.
              </p>
            </>
          ) : null}
          {!model.installed && missingRuntime ? (
            <p className="model-help">
              Requiere {requiresLabel(model.requires ?? '')}: sin él no se puede
              usar, así que no se ofrece instalarlo.
            </p>
          ) : !model.installed ? (
            <button type="button" disabled={busy} onClick={onDownload}>
              Descargar ({formatBytes(model.size_bytes)})
            </button>
          ) : (
            <button
              type="button"
              className="model-danger"
              disabled={busy}
              onClick={onDelete}
            >
              Eliminar
            </button>
          )}
        </div>
      )}

      {failure ? (
        <p className="model-error" role="alert">
          {failure}
        </p>
      ) : null}
      {notice ? (
        <p className="model-error" role="alert">
          {notice}
        </p>
      ) : null}
      {cancelled && !active ? (
        <p className="model-help">Instalación cancelada.</p>
      ) : null}
    </li>
  )
}

export function ModelManager({ onModelsChanged }: ModelManagerProps) {
  const [state, setState] = useState<LoadState>({ phase: 'loading' })
  const [reload, setReload] = useState(0)
  const [dialog, setDialog] = useState<DialogState | null>(null)
  const [busyIds, setBusyIds] = useState<ReadonlySet<string>>(new Set())
  const [notices, setNotices] = useState<Record<string, string>>({})
  const headingId = useId()
  const speakersId = useId()
  const onModelsChangedRef = useRef(onModelsChanged)

  useEffect(() => {
    onModelsChangedRef.current = onModelsChanged
  }, [onModelsChanged])

  const modelsChanged = useCallback(() => {
    setReload((current) => current + 1)
    onModelsChangedRef.current?.()
  }, [])

  const { tasks, error: tasksError, track, refresh } = useModelTasks(modelsChanged)

  useEffect(() => {
    const controller = new AbortController()
    void getModels(controller.signal)
      .then((payload) => {
        setState({ phase: 'ready', payload })
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          setState({ phase: 'error', message: errorMessage(error) })
        }
      })
    return () => {
      controller.abort()
    }
  }, [reload])

  const retry = () => {
    setState({ phase: 'loading' })
    setReload((current) => current + 1)
  }

  const setNotice = (key: string, message: string | null) => {
    setNotices((current) => {
      const next = { ...current }
      if (message === null) {
        delete next[key]
      } else {
        next[key] = message
      }
      return next
    })
  }

  const install = (model: ModelView, method: InstallMethod) => {
    setDialog(null)
    setNotice(model.key, null)
    setBusyIds((current) => new Set(current).add(model.key))
    installModel(model.key, method)
      .then(track)
      .catch((failure: unknown) => {
        setNotice(model.key, errorMessage(failure))
        // 409 model_already_installed / 404 external_model_not_found: la lista quedó vieja.
        setReload((current) => current + 1)
      })
      .finally(() => {
        setBusyIds((current) => {
          const next = new Set(current)
          next.delete(model.key)
          return next
        })
      })
  }

  const cancel = (task: TaskView) => {
    cancelModelTask(task.id)
      .catch((failure: unknown) => {
        setNotice(task.key, errorMessage(failure))
      })
      .finally(refresh)
  }

  const latest = latestByModel(tasks)
  const polling = tasks.some(isActiveTask)
  const models = state.phase === 'ready' ? state.payload.models : []
  const asr = models.filter((m) => m.kind !== 'diarization').sort(compareModels)
  const speakers = models.filter((m) => m.kind === 'diarization')

  const renderList = (list: ModelView[]) => (
    <ul className="model-list">
      {list.map((model) => (
        <ModelRow
          key={model.key}
          model={model}
          task={latest.get(model.key)}
          notice={notices[model.key]}
          busy={busyIds.has(model.key)}
          onImport={() => {
            install(model, 'import')
          }}
          onDownload={() => {
            setDialog({ kind: 'download', model })
          }}
          onDelete={() => {
            setDialog({ kind: 'delete', model })
          }}
          onCancel={cancel}
        />
      ))}
    </ul>
  )

  return (
    <section className="model-manager" aria-labelledby={headingId}>
      <h2 id={headingId}>Modelos</h2>

      {state.phase === 'loading' ? (
        <p aria-live="polite">Consultando los modelos de este equipo…</p>
      ) : state.phase === 'error' ? (
        <div className="model-error" role="alert">
          <p>{state.message}</p>
          <button type="button" onClick={retry}>
            Reintentar
          </button>
        </div>
      ) : (
        <>
          <p className="model-disk">
            Los modelos instalados ocupan{' '}
            <strong>{formatBytes(state.payload.disk.models_bytes)}</strong>
            {' · '}Espacio libre:{' '}
            <strong>
              {state.payload.disk.free_bytes === null
                ? 'no disponible'
                : formatBytes(state.payload.disk.free_bytes)}
            </strong>
          </p>
          {tasksError && polling ? (
            <p className="model-error" role="alert">
              No se pudo actualizar el progreso; se sigue intentando.
            </p>
          ) : null}
          {renderList(asr)}
          {speakers.length > 0 ? (
            <section aria-labelledby={speakersId} className="model-speakers">
              <h2 id={speakersId}>Hablantes</h2>
              <p className="model-help">
                Permite activar «Detectar quién habla» en las transcripciones.
                Funciona sin conexión una vez instalado.
              </p>
              {renderList(speakers)}
            </section>
          ) : null}
        </>
      )}

      {dialog?.kind === 'download' && state.phase === 'ready' ? (
        <DownloadDialog
          model={dialog.model}
          freeBytes={state.payload.disk.free_bytes}
          onConfirm={() => {
            install(dialog.model, 'download')
          }}
          onClose={() => {
            setDialog(null)
          }}
        />
      ) : null}
      {dialog?.kind === 'delete' ? (
        <DeleteDialog
          model={dialog.model}
          onDeleted={() => {
            setDialog(null)
            modelsChanged()
          }}
          onClose={() => {
            setDialog(null)
          }}
        />
      ) : null}
    </section>
  )
}
