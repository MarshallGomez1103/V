import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Column,
  FileUploaderDropContainer,
  Grid,
  ProgressBar,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tag,
} from '@carbon/react'

import { isAbortError } from '../api/errors'
import { PROCESSABLE_STATES, type JobState } from '../api/jobs'
import { describeUploadError, uploadMedia, UploadError } from '../api/media'
import { describeProjectError, ProjectError } from '../api/projects'
import { fetchRecordings, type Recording } from '../api/recordings'
import { useI18n } from '../i18n/i18n'
import { formatDuration } from '../lib/formatTime'
import { routeToHash } from '../lib/navigation'
import { Busy } from './Busy'
import { Notice } from './Notice'
import { Panel } from './Panel'
import { ProjectQueue } from './ProjectQueue'
import './ProjectScreen.scss'

export interface ProjectScreenProps {
  projectId: string
  /** Cambia cuando se instala o quita un modelo: refresca las opciones de motor de la cola. */
  modelsVersion?: number
  onOpenJob: (jobId: string) => void
}

interface Upload {
  id: number
  name: string
  status: 'waiting' | 'uploading' | 'done' | 'error'
  fraction: number
  message?: string
}

type Recordings =
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; items: Recording[] }

function tagFor(state: JobState): 'green' | 'red' | 'blue' | 'gray' {
  if (state === 'COMPLETED') {
    return 'green'
  }
  if (state === 'FAILED') {
    return 'red'
  }
  return PROCESSABLE_STATES.has(state) ? 'blue' : 'gray'
}

/** Pantalla de un proyecto: sus grabaciones y la subida de varias, una tras otra. */
export function ProjectScreen({ projectId, modelsVersion = 0, onOpenJob }: ProjectScreenProps) {
  const { t, tn } = useI18n()
  const [recordings, setRecordings] = useState<Recordings>({ phase: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [uploads, setUploads] = useState<Upload[]>([])

  const queue = useRef<{ id: number; file: File }[]>([])
  const running = useRef(false)
  const lastId = useRef(0)
  const unmounted = useRef<AbortController | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    unmounted.current = controller
    return () => {
      controller.abort()
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void fetchRecordings(projectId, controller.signal)
      .then((items) => {
        setRecordings({ phase: 'ready', items })
        // Las subidas terminadas ya están en la tabla.
        setUploads((list) => list.filter((upload) => upload.status !== 'done'))
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          setRecordings({
            phase: 'error',
            message: error instanceof ProjectError ? error.message : describeProjectError('generic'),
          })
        }
      })
    return () => {
      controller.abort()
    }
  }, [projectId, attempt])

  const reload = useCallback(() => {
    setRecordings((current) => (current.phase === 'error' ? { phase: 'loading' } : current))
    setAttempt((current) => current + 1)
  }, [])

  const patch = useCallback((id: number, change: Partial<Upload>) => {
    setUploads((list) => list.map((upload) => (upload.id === id ? { ...upload, ...change } : upload)))
  }, [])

  // Un solo archivo a la vez; un error se anota en su fila y la cola sigue.
  const drain = useCallback(async () => {
    const signal = unmounted.current?.signal
    if (running.current || !signal) {
      return
    }
    running.current = true
    try {
      for (let next = queue.current.shift(); next; next = queue.current.shift()) {
        patch(next.id, { status: 'uploading' })
        try {
          await uploadMedia(projectId, next.file, {
            signal,
            onProgress: (fraction) => {
              patch(next.id, { fraction })
            },
          })
          patch(next.id, { status: 'done', fraction: 1 })
        } catch (error: unknown) {
          if (signal.aborted) {
            return
          }
          patch(next.id, {
            status: 'error',
            message:
              error instanceof UploadError ? describeUploadError(error.code) : describeUploadError('generic'),
          })
        }
      }
    } finally {
      running.current = false
    }
    reload()
  }, [patch, projectId, reload])

  const addFiles = (files: File[]) => {
    if (files.length === 0) {
      return
    }
    const added = files.map((file) => ({ id: ++lastId.current, file }))
    queue.current.push(...added)
    const rows = added.map(({ id, file }): Upload => ({ id, name: file.name, status: 'waiting', fraction: 0 }))
    // Con la cola parada, los avisos de la tanda anterior se descartan.
    setUploads((list) => (running.current ? [...list, ...rows] : rows))
    void drain()
  }

  const items = recordings.phase === 'ready' ? recordings.items : []

  return (
    <Grid narrow className="voz-grid">
      <Column sm={4} md={8} lg={16}>
        <header className="voz-page__header">
          <h1 className="voz-page__title">{t('project.title')}</h1>
          <p className="voz-page__description">{t('project.description')}</p>
        </header>

        <Panel titleId="project-upload-title" title={t('project.upload.title')}>
          <div className="voz-dropzone">
            <FileUploaderDropContainer
              labelText={t('project.drop')}
              multiple
              onAddFiles={(_event, { addedFiles }) => {
                addFiles(addedFiles)
              }}
            />
            <p className="voz-field-note">{t('import.formats')}</p>
          </div>

          {uploads.length > 0 ? (
            <ul className="voz-project__uploads">
              {uploads.map((upload) => (
                <li key={upload.id}>
                  {upload.status === 'error' ? (
                    <Notice
                      kind="error"
                      title={t('project.upload.failed', { name: upload.name })}
                      {...(upload.message ? { subtitle: upload.message } : {})}
                    />
                  ) : (
                    <ProgressBar
                      label={upload.name}
                      value={Math.round(upload.fraction * 100)}
                      max={100}
                      status={upload.status === 'done' ? 'finished' : 'active'}
                      helperText={
                        upload.status === 'waiting'
                          ? t('project.upload.waiting')
                          : upload.status === 'done'
                            ? t('job.stage.state.done')
                            : t('project.upload.progress', { pct: Math.round(upload.fraction * 100) })
                      }
                    />
                  )}
                </li>
              ))}
            </ul>
          ) : null}
        </Panel>

        <Panel
          titleId="project-recordings-title"
          title={t('project.recordings.title')}
          description={recordings.phase === 'ready' ? tn('project.count', items.length) : undefined}
          className="voz-project__recordings"
        >
          {recordings.phase === 'loading' ? <Busy description={t('lib.loading')} /> : null}
          {recordings.phase === 'error' ? (
            <Notice
              kind="error"
              title={t('project.error.title')}
              subtitle={recordings.message}
              action={{ label: t('common.retry'), onClick: reload }}
            />
          ) : null}
          {recordings.phase === 'ready' && items.length === 0 ? (
            <p className="voz-field-note" role="status">
              {t('project.empty')}
            </p>
          ) : null}
          {items.length > 0 ? (
            <Table aria-label={t('project.recordings.table')}>
              <TableHead>
                <TableRow>
                  <TableHeader>{t('lib.col.name')}</TableHeader>
                  <TableHeader>{t('lib.col.duration')}</TableHeader>
                  <TableHeader>{t('lib.col.state')}</TableHeader>
                </TableRow>
              </TableHead>
              <TableBody>
                {items.map((item) => {
                  const job = item.latest_job
                  return (
                    <TableRow key={item.media_asset_id}>
                      <TableCell>
                        {job ? (
                          <a
                            className="voz-project__link"
                            href={routeToHash({ name: 'trabajo', jobId: job.id })}
                            onClick={(event) => {
                              if (!event.metaKey && !event.ctrlKey && !event.shiftKey) {
                                event.preventDefault()
                                onOpenJob(job.id)
                              }
                            }}
                          >
                            {item.filename}
                          </a>
                        ) : (
                          item.filename
                        )}
                      </TableCell>
                      <TableCell>{item.duration_ms === null ? '—' : formatDuration(item.duration_ms)}</TableCell>
                      <TableCell>
                        {job ? (
                          <Tag type={tagFor(job.state)} size="md">
                            {t(`job.state.${job.state}`)}
                          </Tag>
                        ) : (
                          <Tag type="gray" size="md">
                            {t('lib.state.none')}
                          </Tag>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          ) : null}
        </Panel>

        {items.length > 0 ? (
          <ProjectQueue projectId={projectId} modelsVersion={modelsVersion} onOpenJob={onOpenJob} onChanged={reload} />
        ) : null}
      </Column>
    </Grid>
  )
}
