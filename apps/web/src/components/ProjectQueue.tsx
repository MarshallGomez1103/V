import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import {
  Accordion,
  AccordionItem,
  Button,
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
import { cancelJob, messageForFailure } from '../api/jobs'
import {
  cancelQueue,
  getProjectQueue,
  QueueError,
  startQueue,
  type QueueItemStatus,
  type QueueView,
  type SkippedRecording,
} from '../api/transcriptionQueue'
import { useDiarizationModel } from '../hooks/useDiarizationModel'
import { useI18n, type I18n, type Translate } from '../i18n/i18n'
import type { MessageKey } from '../i18n/messages'
import { failureMessage } from '../lib/jobFailure'
import { routeToHash } from '../lib/navigation'
import { DiarizationOptions, type DiarizationRequest } from './DiarizationOptions'
import { Busy } from './Busy'
import { Notice } from './Notice'
import { Panel } from './Panel'
import { TranscriptionOptionsSelector } from './TranscriptionOptionsSelector'
import './ProjectQueue.scss'

export interface ProjectQueueProps {
  projectId: string
  /** Cambia cuando se instala o quita un modelo: refresca las opciones de motor. */
  modelsVersion: number
  onOpenJob: (jobId: string) => void
  /** Se llama una vez cuando la cola pasa de en curso a terminada (p. ej. para recargar la tabla). */
  onChanged?: () => void
}

type Load =
  | { phase: 'loading' }
  | { phase: 'error'; message: string | null }
  | { phase: 'ready'; queue: QueueView | null }

const POLL_MS = 1000
const POLL_FAILURES_BEFORE_NOTICE = 3

const TAG_TYPE: Record<QueueItemStatus, 'green' | 'red' | 'blue' | 'gray'> = {
  done: 'green',
  error: 'red',
  running: 'blue',
  pending: 'gray',
  cancelled: 'gray',
}

const REASON_ORDER = ['already_transcribed', 'job_active', 'duration_unknown'] as const

const SKIPPED_LABEL: Record<string, MessageKey> = {
  already_transcribed: 'queue.skipped.already_transcribed',
  job_active: 'queue.skipped.job_active',
  duration_unknown: 'queue.skipped.duration_unknown',
}

function summarize(queue: QueueView, t: Translate, tn: I18n['tn']): string {
  const { counts, skipped } = queue
  const parts = [t('queue.sum.done', { done: counts.done, total: counts.total })]
  if (counts.error > 0) {
    parts.push(t('queue.sum.error', { n: counts.error }))
  }
  if (counts.cancelled > 0) {
    parts.push(tn('queue.sum.cancelled', counts.cancelled))
  }
  if (counts.skipped > 0) {
    const count = (reason: string) => skipped.filter((entry) => entry.reason === reason).length
    const known = REASON_ORDER.map((reason) => [reason, count(reason)] as const)
    const other = skipped.length - known.reduce((sum, [, n]) => sum + n, 0)
    const reasons = known
      .filter(([, n]) => n > 0)
      .map(([reason, n]) =>
        reason === 'already_transcribed'
          ? tn('queue.reason.already_transcribed', n)
          : t(reason === 'job_active' ? 'queue.reason.job_active' : 'queue.reason.duration_unknown', { n }),
      )
    if (other > 0) {
      reasons.push(t('queue.reason.other', { n: other }))
    }
    parts.push(tn('queue.sum.skipped', counts.skipped, { reasons: reasons.join(', ') }))
  }
  return parts.join(' · ')
}

function SkippedList({ skipped }: { skipped: SkippedRecording[] }) {
  const { t } = useI18n()
  return (
    <div className="voz-queue__skipped">
      <h3 className="voz-queue__subtitle">{t('queue.skipped.title')}</h3>
      <ul>
        {skipped.map((entry) => (
          <li key={entry.media_asset_id}>
            <span>{entry.filename}</span>
            <span className="voz-queue__reason">
              {t(Object.hasOwn(SKIPPED_LABEL, entry.reason) ? (SKIPPED_LABEL[entry.reason] as MessageKey) : 'queue.skipped.other')}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

interface QueueStartProps {
  projectId: string
  modelsVersion: number
  onStarted: (queue: QueueView) => void
  /** Ya hay otra cola activa: el padre la vuelve a consultar. */
  onConflict: () => void
}

/** Motor local y hablantes para «Transcribir proyecto». */
function QueueStart({ projectId, modelsVersion, onStarted, onConflict }: QueueStartProps) {
  const { t } = useI18n()
  const [optionId, setOptionId] = useState<string | null>(null)
  const [diarization, setDiarization] = useState<DiarizationRequest>({ enabled: false, speakers: {} })
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<QueueError | null>(null)
  const diarModel = useDiarizationModel(diarization.enabled, modelsVersion)

  const diarBlocked = diarization.enabled && diarModel.status !== 'ready'
  const canStart = optionId !== null && !starting && !diarBlocked
  const whyNot = starting
    ? null
    : optionId === null
      ? t('cfg.why.option')
      : diarBlocked
        ? t('diar.blocked')
        : null

  const start = async () => {
    if (!canStart) {
      return
    }
    setStarting(true)
    setError(null)
    try {
      onStarted(await startQueue(projectId, { option_id: optionId, language: null, diarization }))
    } catch (failure: unknown) {
      setError(failure instanceof QueueError ? failure : new QueueError('network', t('err.network')))
      if (failure instanceof QueueError && failure.code === 'transcription_queue_active') {
        onConflict()
      }
    } finally {
      setStarting(false)
    }
  }

  return (
    <Panel
      titleId="project-queue-start-title"
      title={t('queue.start.title')}
      description={t('queue.start.desc')}
      className="voz-queue"
    >
      <TranscriptionOptionsSelector
        localOnly
        refreshKey={modelsVersion}
        value={optionId}
        onChange={setOptionId}
        disabled={starting}
      />
      <Accordion isFlush>
        <AccordionItem title={t('spk.title')}>
          <DiarizationOptions value={diarization} onChange={setDiarization} disabled={starting} model={diarModel} />
        </AccordionItem>
      </Accordion>
      {error ? (
        <div className="voz-queue__failure">
          <Notice kind="error" title={t('queue.error.start')} subtitle={error.message} />
          {error.skipped.length > 0 ? <SkippedList skipped={error.skipped} /> : null}
        </div>
      ) : null}
      <div className="voz-queue__actions">
        <Button
          kind="primary"
          size="lg"
          disabled={!canStart}
          onClick={() => {
            void start()
          }}
        >
          {starting ? t('queue.starting') : t('queue.start')}
        </Button>
        {whyNot ? (
          <p className="voz-field-note" role="status">
            {whyNot}
          </p>
        ) : null}
      </div>
    </Panel>
  )
}

interface QueuePanelProps {
  queue: QueueView
  acting: boolean
  error: string | null
  /** El sondeo lleva varios fallos seguidos. */
  pollFailed: boolean
  /** Destino estable del foco cuando desaparece el control que lo tenía. */
  summaryRef: RefObject<HTMLParagraphElement | null>
  onCancelQueue: () => void
  /** Avisa de que «Cancelar cola» tiene (o dejó de tener) el foco. */
  onCancelFocus: (focused: boolean) => void
  onCancelItem: (jobId: string) => void
  onOpenJob: (jobId: string) => void
}

function QueuePanel({
  queue,
  acting,
  error,
  pollFailed,
  summaryRef,
  onCancelQueue,
  onCancelFocus,
  onCancelItem,
  onOpenJob,
}: QueuePanelProps) {
  const { t, tn } = useI18n()
  const running = queue.state === 'running'
  const pct = Math.round(queue.progress * 100)

  return (
    <Panel
      titleId="project-queue-title"
      title={t('queue.title')}
      className="voz-queue"
      actions={
        running ? (
          <Button
            kind="danger--tertiary"
            size="sm"
            disabled={acting}
            onClick={onCancelQueue}
            onFocus={() => {
              onCancelFocus(true)
            }}
            onBlur={(event) => {
              // Sin destino (relatedTarget nulo) es que el botón se quitó del DOM: se conserva la marca.
              if (event.relatedTarget) {
                onCancelFocus(false)
              }
            }}
          >
            {t('queue.cancel')}
          </Button>
        ) : undefined
      }
    >
      <ProgressBar
        label={t('queue.progress')}
        value={pct}
        max={100}
        status={running ? 'active' : queue.counts.error > 0 ? 'error' : 'finished'}
        helperText={t('job.progress.pct', { pct })}
      />
      <p ref={summaryRef} tabIndex={-1} className="voz-queue__summary" aria-live="polite">
        {summarize(queue, t, tn)}
      </p>
      {running && pollFailed ? <Notice kind="warning" title={t('queue.error.load')} /> : null}
      {error ? <Notice kind="error" title={t('queue.error.cancel')} subtitle={error} /> : null}
      <Table aria-label={t('queue.table')}>
        <TableHead>
          <TableRow>
            <TableHeader>{t('lib.col.name')}</TableHeader>
            <TableHeader>{t('lib.col.state')}</TableHeader>
            <TableHeader>{t('queue.col.actions')}</TableHeader>
          </TableRow>
        </TableHead>
        <TableBody>
          {queue.items.map((item) => (
            <TableRow key={item.job_id}>
              <TableCell>{item.filename}</TableCell>
              <TableCell>
                <Tag type={TAG_TYPE[item.status]} size="md">
                  {t(`job.state.${item.job_state}`) +
                    (item.status === 'running' ? ' · ' + t('job.progress.pct', { pct: Math.round(item.progress * 100) }) : '')}
                </Tag>
                {item.status === 'error' ? <p className="voz-queue__reason">{failureMessage(item.error_code)}</p> : null}
              </TableCell>
              <TableCell>
                {item.status === 'done' ? (
                  <a
                    className="voz-queue__link"
                    href={routeToHash({ name: 'trabajo', jobId: item.job_id })}
                    aria-label={t('lib.open.named', { name: item.filename })}
                    onClick={(event) => {
                      if (!event.metaKey && !event.ctrlKey && !event.shiftKey) {
                        event.preventDefault()
                        onOpenJob(item.job_id)
                      }
                    }}
                  >
                    {t('lib.open')}
                  </a>
                ) : null}
                {item.status === 'pending' || item.status === 'running' ? (
                  <Button
                    kind="ghost"
                    size="sm"
                    disabled={acting || item.job_state === 'CANCELLING'}
                    aria-label={t('queue.item.cancel', { name: item.filename })}
                    onClick={() => {
                      onCancelItem(item.job_id)
                    }}
                  >
                    {t('job.cancel')}
                  </Button>
                ) : null}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {queue.skipped.length > 0 ? <SkippedList skipped={queue.skipped} /> : null}
    </Panel>
  )
}

/** Cola «Transcribir proyecto»: iniciarla, seguirla ítem por ítem y cancelarla. */
export function ProjectQueue({ projectId, modelsVersion, onOpenJob, onChanged }: ProjectQueueProps) {
  const { t } = useI18n()
  const [load, setLoad] = useState<Load>({ phase: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [acting, setActing] = useState(false)
  const [actionError, setActionError] = useState<{ queueId: string; message: string } | null>(null)
  const [pollFailed, setPollFailed] = useState(false)
  const summaryRef = useRef<HTMLParagraphElement>(null)
  // El foco estaba en el control que se va a quitar (iniciar o cancelar la cola).
  const keepFocus = useRef(false)
  const unmounted = useRef<AbortController | null>(null)
  const wasRunning = useRef(false)
  const changed = useRef(onChanged)

  useEffect(() => {
    changed.current = onChanged
  }, [onChanged])

  useEffect(() => {
    const controller = new AbortController()
    unmounted.current = controller
    return () => {
      controller.abort()
    }
  }, [])

  const apply = useCallback((queue: QueueView | null) => {
    if (unmounted.current?.signal.aborted) {
      return
    }
    const running = queue?.state === 'running'
    if (wasRunning.current && !running) {
      changed.current?.()
    }
    wasRunning.current = running
    setPollFailed(false)
    setLoad({ phase: 'ready', queue })
  }, [])

  const refresh = useCallback(
    () => getProjectQueue(projectId, unmounted.current?.signal).then(apply, () => undefined),
    [apply, projectId],
  )

  useEffect(() => {
    const controller = new AbortController()
    getProjectQueue(projectId, controller.signal).then(apply, (failure: unknown) => {
      if (!isAbortError(failure)) {
        setLoad({
          phase: 'error',
          message: failure instanceof QueueError ? failure.message : null,
        })
      }
    })
    return () => {
      controller.abort()
    }
  }, [apply, attempt, projectId])

  const queue = load.phase === 'ready' ? load.queue : null
  const running = queue?.state === 'running'

  // Si el control enfocado se quitó, el foco cae en <body>: se lleva al resumen de la cola.
  useEffect(() => {
    if (keepFocus.current && summaryRef.current && (!document.activeElement || document.activeElement === document.body)) {
      summaryRef.current.focus()
      keepFocus.current = false
    }
  }, [load])

  // ponytail: sondeo cada segundo mientras la cola corre; techo: SSE de cola, como los eventos de un trabajo.
  useEffect(() => {
    if (!running) {
      return
    }
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    let failures = 0
    const schedule = () => {
      timer = setTimeout(() => {
        getProjectQueue(projectId, controller.signal).then(
          (next) => {
            failures = 0
            apply(next)
            if (!controller.signal.aborted && next?.state === 'running') {
              schedule()
            }
          },
          () => {
            if (!controller.signal.aborted) {
              failures += 1
              if (failures >= POLL_FAILURES_BEFORE_NOTICE) {
                setPollFailed(true)
              }
              schedule()
            }
          },
        )
      }, POLL_MS)
    }
    schedule()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [apply, projectId, running])

  const act = async (action: () => Promise<void>) => {
    setActing(true)
    setActionError(null)
    try {
      await action()
    } catch (failure: unknown) {
      setActionError({
        queueId: queue?.id ?? '',
        message: failure instanceof QueueError ? failure.message : messageForFailure(failure),
      })
      await refresh()
    } finally {
      setActing(false)
    }
  }

  if (load.phase === 'loading') {
    return <Busy description={t('common.loading')} />
  }
  if (load.phase === 'error') {
    return (
      <Notice
        kind="error"
        title={t('queue.error.load')}
        subtitle={load.message ?? t('err.network')}
        action={{
          label: t('common.retry'),
          onClick: () => {
            setLoad({ phase: 'loading' })
            setAttempt((current) => current + 1)
          },
        }}
      />
    )
  }

  return (
    <>
      {queue ? (
        <QueuePanel
          queue={queue}
          acting={acting}
          error={actionError?.queueId === queue.id && running ? actionError.message : null}
          pollFailed={pollFailed}
          summaryRef={summaryRef}
          onCancelFocus={(focused) => {
            keepFocus.current = focused
          }}
          onCancelQueue={() => {
            keepFocus.current = true
            void act(async () => {
              apply(await cancelQueue(queue.id, unmounted.current?.signal))
            })
          }}
          onCancelItem={(jobId) => {
            void act(async () => {
              await cancelJob(jobId)
              await refresh()
            })
          }}
          onOpenJob={onOpenJob}
        />
      ) : null}
      {running ? null : (
        <QueueStart
          projectId={projectId}
          modelsVersion={modelsVersion}
          onStarted={(started) => {
            keepFocus.current = true
            apply(started)
          }}
          onConflict={() => void refresh()}
        />
      )}
    </>
  )
}
