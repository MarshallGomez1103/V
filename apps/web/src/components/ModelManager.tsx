import { useCallback, useEffect, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  Button,
  DataTable,
  Modal,
  ProgressBar,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  Tag,
  TextInput,
} from '@carbon/react'
import { ErrorFilled, TrashCan } from '@carbon/icons-react'

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
import { translate, useI18n, type Translate } from '../i18n/i18n'
import { formatBytes } from '../lib/formatBytes'
import { compareModelIds } from '../lib/modelOrder'
import { Busy } from './Busy'
import { Term } from './Hint'
import { Notice } from './Notice'
import { ProcessingProfileLabel } from './TechTerms'
import './ModelManager.scss'

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

const RECOMMENDED_KEY = 'faster-whisper:turbo'

/** Runtime externo que cada familia necesita, en lenguaje del usuario. */
function requiresLabel(requires: string, t: Translate): string {
  return requires === 'diarization' ? t('mm.requires.diarization') : requires
}

/** faster-whisper primero, luego el resto de proveedores; dentro, orden de catálogo. */
function compareModels(a: ModelView, b: ModelView): number {
  const home = (m: ModelView) => (m.provider_id === 'faster-whisper' ? 0 : 1)
  return home(a) - home(b) || compareModelIds(a.model_id, b.model_id)
}

function errorMessage(error: unknown): string {
  return error instanceof ModelApiError ? error.message : translate('err.model.op')
}

function taskPercent(task: TaskView): number | null {
  return task.total_bytes > 0
    ? Math.min(100, Math.floor((task.done_bytes / task.total_bytes) * 100))
    : null
}

function describeTask(task: TaskView, t: Translate): string {
  if (task.state === 'queued') {
    return t('mm.task.queued')
  }
  const verb = task.method === 'import' ? t('mm.task.copying') : t('mm.task.downloading')
  const percent = taskPercent(task)
  return percent === null
    ? verb + '…'
    : t('mm.task.progress', {
        verb,
        pct: percent,
        done: formatBytes(task.done_bytes),
        total: formatBytes(task.total_bytes),
      })
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

/** Al desmontar un diálogo, el foco vuelve al control que lo abrió (si sigue en pantalla). */
function useRestoreFocus() {
  useEffect(() => {
    const opener = document.activeElement
    return () => {
      // ponytail: si el disparador ya no existe (p. ej. pasó a mostrar progreso) el foco cae al body.
      if (opener instanceof HTMLElement && opener.isConnected) {
        opener.focus()
      }
    }
  }, [])
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
  useRestoreFocus()
  const { t } = useI18n()
  const insufficient = freeBytes !== null && freeBytes < model.size_bytes
  const from =
    model.kind === 'diarization' ? 'GitHub' : 'HuggingFace (' + String(model.source) + ')'
  return (
    <Modal
      open
      size="sm"
      closeButtonLabel={t('common.close')}
      modalHeading={t('mm.download.title', { name: model.display_name })}
      primaryButtonText={t('mm.download.confirm')}
      secondaryButtonText={t('common.cancel')}
      onRequestClose={onClose}
      onRequestSubmit={onConfirm}
    >
      <p>{t('mm.download.body', { size: formatBytes(model.size_bytes), from })}</p>
      {insufficient ? (
        <Notice
          kind="warning"
          role="alert"
          title={t('mm.download.lowSpace', { free: formatBytes(freeBytes) })}
        />
      ) : null}
    </Modal>
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
  useRestoreFocus()
  const { t } = useI18n()
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputId = useId()
  const matches = typed === model.model_id

  const submit = (event?: FormEvent) => {
    event?.preventDefault()
    if (!matches || busy) {
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
    <Modal
      open
      danger
      size="sm"
      closeButtonLabel={t('common.close')}
      modalHeading={t('mm.delete.title', { name: model.display_name })}
      primaryButtonText={busy ? t('mm.delete.busy') : t('common.delete')}
      secondaryButtonText={t('common.cancel')}
      primaryButtonDisabled={!matches || busy}
      shouldSubmitOnEnter
      onRequestClose={onClose}
      onRequestSubmit={() => {
        submit()
      }}
    >
      <p>{t('mm.delete.body', { size: formatBytes(model.disk_bytes ?? model.size_bytes) })}</p>
      <TextInput
        id={inputId}
        data-modal-primary-focus
        labelText={
          <>
            {t('mm.delete.confirmLabel')} <code>{model.model_id}</code>
          </>
        }
        value={typed}
        autoComplete="off"
        spellCheck={false}
        onChange={(event) => {
          setTyped(event.target.value)
        }}
      />
      {error ? <Notice kind="error" title={error} /> : null}
    </Modal>
  )
}

interface ModelCellProps {
  model: ModelView
  task: TaskView | undefined
  notice: string | undefined
  busy: boolean
  onImport: () => void
  onDownload: () => void
  onDelete: () => void
  onCancel: (task: TaskView) => void
}

function localCopy(model: ModelView): boolean {
  // El backend marca con `origin` de dónde viene la copia; la UI no nombra la app.
  return model.external.some((entry) => entry.origin === 'buzz')
}

function statusOf(model: ModelView, t: Translate): string {
  return model.installed
    ? t('mm.status.installed')
    : localCopy(model)
      ? t('mm.status.local')
      : t('mm.status.missing')
}

function StatusTag({ model }: { model: ModelView }) {
  const { t } = useI18n()
  const hint = model.installed
    ? 'mm.status.installed.def'
    : localCopy(model)
      ? 'mm.status.local.def'
      : 'mm.status.missing.def'
  return (
    <Tag
      size="md"
      type={model.installed ? 'green' : localCopy(model) ? 'cyan' : 'gray'}
    >
      <Term definition={hint}>{statusOf(model, t)}</Term>
    </Tag>
  )
}

function NameCell({ model, task, notice }: Pick<ModelCellProps, 'model' | 'task' | 'notice'>) {
  const { t } = useI18n()
  const failure =
    !model.installed && task?.state === 'failed'
      ? messageForModelError(task.error_code ?? 'model_task_failed')
      : null
  const cancelled = !model.installed && task?.state === 'cancelled'
  const missingRuntime = !model.runtime_available && model.requires !== null
  return (
    <div className="voz-model">
      <div className="voz-model__head">
        <strong className="voz-model__name">{model.display_name}</strong>
        {model.key === RECOMMENDED_KEY ? (
          <Tag type="green" size="sm">
            <Term definition="opt.recommended.def">{t('opt.recommended')}</Term>
          </Tag>
        ) : null}
      </div>
      {model.requires !== null ? (
        <span className="voz-model__sub">
          {t('mm.requires', { what: requiresLabel(model.requires, t) }) +
            (!model.installed && missingRuntime ? t('mm.requires.blocked') : '')}
        </span>
      ) : null}
      {failure ? (
        <span className="voz-model__error" role="alert">
          <ErrorFilled size={16} aria-hidden="true" />
          {failure}
        </span>
      ) : null}
      {notice ? (
        <span className="voz-model__error" role="alert">
          <ErrorFilled size={16} aria-hidden="true" />
          {notice}
        </span>
      ) : null}
      {cancelled ? <span className="voz-model__sub">{t('mm.cancelled')}</span> : null}
    </div>
  )
}

function ActionsCell({
  model,
  task,
  busy,
  onImport,
  onDownload,
  onDelete,
  onCancel,
}: Omit<ModelCellProps, 'notice'>) {
  const { t } = useI18n()
  const helpId = useId()
  const missingRuntime = !model.runtime_available && model.requires !== null
  const active = task && isActiveTask(task) ? task : undefined
  const percent = active ? taskPercent(active) : null

  if (active) {
    return (
      <div className="voz-model__progress" role="status">
        <ProgressBar
          size="small"
          hideLabel
          label={t('mm.progress', { name: model.display_name })}
          helperText={describeTask(active, t)}
          {...(active.total_bytes > 0 && percent !== null
            ? { value: active.done_bytes, max: active.total_bytes }
            : {})}
        />
        <Button
          kind="ghost"
          size="sm"
          onClick={() => {
            onCancel(active)
          }}
        >
          {t('common.cancel')}
        </Button>
      </div>
    )
  }

  return (
    <div className="voz-model__actions">
      {!model.installed && !missingRuntime && localCopy(model) ? (
        <>
          <Button
            kind="primary"
            size="sm"
            disabled={busy}
            aria-describedby={helpId}
            onClick={onImport}
          >
            {t('mm.useLocal')}
          </Button>
          <span className="voz-model__sub" id={helpId}>
            {t('mm.useLocal.help')}
          </span>
        </>
      ) : null}
      {!model.installed && !missingRuntime ? (
        <Button kind="tertiary" size="sm" disabled={busy} onClick={onDownload}>
          {t('mm.download', { size: formatBytes(model.size_bytes) })}
        </Button>
      ) : null}
      {model.installed ? (
        <Button
          kind="danger--ghost"
          size="sm"
          renderIcon={TrashCan}
          disabled={busy}
          onClick={onDelete}
        >
          {t('common.delete')}
        </Button>
      ) : null}
    </div>
  )
}

/** Texto accesible del orden de columnas (Carbon lo trae en inglés). */
function sortLabel(
  _id: string,
  args?: { header?: unknown; sortDirection?: unknown; isSortHeader?: boolean },
): string {
  const header = typeof args?.header === 'string' ? args.header : ''
  if (!args?.isSortHeader || args.sortDirection === 'NONE') {
    return translate('mm.sort.asc', { header })
  }
  return args.sortDirection === 'ASC'
    ? translate('mm.sort.desc', { header })
    : translate('mm.sort.clear', { header })
}

interface ModelTableProps {
  label: string
  onCancel: (task: TaskView) => void
  models: ModelView[]
  latest: Map<string, TaskView>
  notices: Record<string, string>
  onImportModel: (model: ModelView) => void
  onDownloadModel: (model: ModelView) => void
  onDeleteModel: (model: ModelView) => void
  busyIds: ReadonlySet<string>
}

function ModelTable({
  label,
  models,
  latest,
  notices,
  busyIds,
  onImportModel,
  onDownloadModel,
  onDeleteModel,
  onCancel,
}: ModelTableProps) {
  const { t } = useI18n()
  const headers = [
    { key: 'name', header: t('mm.col.model') },
    { key: 'status', header: t('mm.col.status') },
    { key: 'profile', header: t('mm.col.profile') },
    { key: 'size', header: t('mm.col.size') },
    { key: 'license', header: t('mm.col.license') },
    { key: 'actions', header: t('mm.col.actions') },
  ]
  const byKey = new Map(models.map((model) => [model.key, model]))
  const rows = models.map((model) => ({
    id: model.key,
    name: model.display_name,
    status: statusOf(model, t),
    profile: model.profile ?? '',
    size: model.size_bytes,
    license: model.license,
    actions: '',
  }))

  return (
    <DataTable rows={rows} headers={headers} isSortable size="lg">
      {({ rows: tableRows, headers, getHeaderProps, getRowProps, getTableProps }) => (
        <TableContainer aria-label={label}>
          <Table {...getTableProps()} aria-label={label}>
            <TableHead>
              <TableRow>
                {headers.map((header) => {
                  const { key, isSortable, ...headerProps } = getHeaderProps({
                    header,
                    isSortable: header.key !== 'actions',
                  })
                  return (
                    <TableHeader
                      key={key}
                      isSortable={isSortable === true}
                      translateWithId={sortLabel}
                      {...headerProps}
                    >
                      {header.header}
                    </TableHeader>
                  )
                })}
              </TableRow>
            </TableHead>
            <TableBody>
              {tableRows.map((row) => {
                const model = byKey.get(row.id)
                if (!model) {
                  return null
                }
                const task = latest.get(model.key)
                const { key, ...rowProps } = getRowProps({ row })
                return (
                  <TableRow key={key} {...rowProps}>
                    <TableCell>
                      <NameCell model={model} task={task} notice={notices[model.key]} />
                    </TableCell>
                    <TableCell>
                      <StatusTag model={model} />
                    </TableCell>
                    <TableCell>
                      {model.profile === null ? (
                        '—'
                      ) : (
                        <ProcessingProfileLabel name={model.profile} />
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="voz-model__size">
                        <span>{formatBytes(model.size_bytes)}</span>
                        {model.installed && model.disk_bytes !== null && model.disk_bytes > 0 ? (
                          <span className="voz-model__sub">
                            {t('mm.onDisk', { size: formatBytes(model.disk_bytes) })}
                          </span>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell>{model.license}</TableCell>
                    <TableCell>
                      <ActionsCell
                        model={model}
                        task={task}
                        busy={busyIds.has(model.key)}
                        onImport={() => {
                          onImportModel(model)
                        }}
                        onDownload={() => {
                          onDownloadModel(model)
                        }}
                        onDelete={() => {
                          onDeleteModel(model)
                        }}
                        onCancel={onCancel}
                      />
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </DataTable>
  )
}

export function ModelManager({ onModelsChanged }: ModelManagerProps) {
  const { t } = useI18n()
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

  const renderTable = (label: string, list: ModelView[]) => (
    <ModelTable
      label={label}
      models={list}
      latest={latest}
      notices={notices}
      busyIds={busyIds}
      onCancel={cancel}
      onImportModel={(model) => {
        install(model, 'import')
      }}
      onDownloadModel={(model) => {
        setDialog({ kind: 'download', model })
      }}
      onDeleteModel={(model) => {
        setDialog({ kind: 'delete', model })
      }}
    />
  )

  return (
    <section className="voz-models" aria-labelledby={headingId}>
      <h2 id={headingId} className="voz-section-title">
        {t('mm.engines')}
      </h2>

      {state.phase === 'loading' ? (
        <div aria-live="polite">
          <Busy description={t('opt.loading')} />
        </div>
      ) : state.phase === 'error' ? (
        <Notice
          kind="error"
          title={t('mm.error.title')}
          subtitle={state.message}
          action={{ label: t('common.retry'), onClick: retry }}
        />
      ) : (
        <>
          <p className="voz-models__disk">
            {t('mm.disk.used')} <strong>{formatBytes(state.payload.disk.models_bytes)}</strong>
            {' · '}
            {t('mm.disk.free')}{' '}
            <strong>
              {state.payload.disk.free_bytes === null
                ? t('mm.disk.unknown')
                : formatBytes(state.payload.disk.free_bytes)}
            </strong>
          </p>
          {tasksError && polling ? (
            <Notice
              kind="error"
              title={t('mm.tasks.error')}
            />
          ) : null}
          {asr.length > 0 ? renderTable(t('mm.engines'), asr) : null}
          {speakers.length > 0 ? (
            <section aria-labelledby={speakersId} className="voz-models__speakers">
              <h2 id={speakersId} className="voz-section-title">
                {t('spk.title')}
              </h2>
              <p className="voz-section-description">{t('mm.speakers.desc')}</p>
              {renderTable(t('mm.speakers.table'), speakers)}
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
