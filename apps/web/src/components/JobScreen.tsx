import type { ReactNode } from 'react'
import { Button, ProgressBar } from '@carbon/react'
import { Checkmark, ErrorFilled, StopFilledAlt } from '@carbon/icons-react'

import {
  PROCESSABLE_STATES,
  type JobState,
  type JobView,
} from '../api/jobs'
import { useCloudProviders } from '../hooks/useCloudProviders'
import { useNow } from '../hooks/useNow'
import { useI18n, type Translate } from '../i18n/i18n'
import type { MessageKey } from '../i18n/messages'
import { formatSeconds } from '../lib/formatTime'
import { parseIso } from '../lib/time'
import { Busy } from './Busy'
import { CloudBadge } from './CloudBadge'
import { Term } from './Hint'
import { Notice } from './Notice'
import { Panel } from './Panel'
import { DeviceLabel, ProcessingProfileLabel } from './TechTerms'
import './JobScreen.scss'

interface JobScreenProps {
  job: JobView | null
  loading?: boolean
  error?: string | null
  onCancel?: () => void
  /** Vuelve a la configuración con la misma grabación (fallo, cancelación o repetir). */
  onAdjust?: () => void
}

type Stage = 'prepare' | 'transcribe' | 'speakers' | 'finish'

const STAGE_OF: Record<JobState, Stage | 'done'> = {
  QUEUED: 'prepare',
  PROBING: 'prepare',
  PREPROCESSING: 'prepare',
  TRANSCRIBING: 'transcribe',
  ALIGNING: 'transcribe',
  DIARIZING: 'speakers',
  MERGING: 'finish',
  PERSISTING: 'finish',
  COMPLETED: 'done',
  FAILED: 'done',
  CANCELLING: 'done',
  CANCELLED: 'done',
}

function readString(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value))
}

type StageStatus = 'done' | 'current' | 'pending' | 'failed'

interface StageView {
  id: Stage
  status: StageStatus
  /** 0..1 si se conoce; null = sin medida (barra indeterminada si está en curso). */
  fraction: number | null
}

/** Etapas visibles: «Hablantes» solo si se pidieron (o ya se está ejecutando). */
function buildStages(job: JobView): StageView[] {
  const withSpeakers =
    job.selection?.diarization?.enabled === true || job.state === 'DIARIZING'
  const order: Stage[] = withSpeakers
    ? ['prepare', 'transcribe', 'speakers', 'finish']
    : ['prepare', 'transcribe', 'finish']
  const where = STAGE_OF[job.state]
  const stageProgress =
    typeof job.stage_progress === 'number' ? clamp01(job.stage_progress) : null
  const completed = job.state === 'COMPLETED'
  const failed = job.state === 'FAILED'
  // Si el trabajo falló no se sabe en qué etapa: se marca la actual por el último estado conocido.
  const current = where === 'done' ? null : where

  return order.map((id, index) => {
    if (completed) {
      return { id, status: 'done', fraction: 1 }
    }
    if (current === null) {
      return { id, status: failed ? 'failed' : 'pending', fraction: 0 }
    }
    const here = order.indexOf(current)
    if (index < here) {
      return { id, status: 'done', fraction: 1 }
    }
    if (index === here) {
      return { id, status: 'current', fraction: stageProgress }
    }
    return { id, status: 'pending', fraction: 0 }
  })
}

function Stages({ job, t }: { job: JobView; t: Translate }) {
  const stages = buildStages(job)
  const queued = job.state === 'QUEUED'
  return (
    <ol className="voz-stages" aria-label={t('job.stages')}>
      {stages.map((stage, index) => {
        const percent =
          stage.fraction === null ? null : Math.round(stage.fraction * 100)
        const state =
          stage.status === 'current'
            ? queued
              ? 'waiting'
              : 'working'
            : stage.status === 'done'
              ? 'done'
              : stage.status === 'failed'
                ? 'failed'
                : 'pending'
        return (
          <li
            key={stage.id}
            className={'voz-stage voz-stage--' + stage.status}
            {...(stage.status === 'current' ? { 'aria-current': 'step' as const } : {})}
          >
            <span className="voz-stage__label">
              <span className="voz-stage__index" aria-hidden="true">
                {stage.status === 'done' ? (
                  <Checkmark size={16} />
                ) : stage.status === 'failed' ? (
                  <ErrorFilled size={16} />
                ) : (
                  index + 1
                )}
              </span>
              {t(`job.stage.${stage.id}`)}
            </span>
            <span
              className={
                'voz-stage__bar' +
                (stage.status === 'current' && percent === null && !queued
                  ? ' voz-stage__bar--indeterminate'
                  : '')
              }
              aria-hidden="true"
            >
              <span
                className="voz-stage__fill"
                style={{
                  inlineSize:
                    stage.status === 'current' && percent === null
                      ? undefined
                      : String(percent ?? 0) + '%',
                }}
              />
            </span>
            <span className="voz-stage__meta">
              {stage.status === 'current' && percent !== null && !queued
                ? t('job.progress.stagePct', { pct: percent })
                : t(`job.stage.state.${state}`)}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

function Figure({
  label,
  hint,
  children,
}: {
  label: string
  /** Explicación breve en un tooltip sobre la etiqueta. */
  hint?: MessageKey | undefined
  children: ReactNode
}) {
  return (
    <div className="voz-figure">
      <dt className="voz-figure__label">
        {hint ? <Term definition={hint}>{label}</Term> : label}
      </dt>
      <dd className="voz-figure__value">{children}</dd>
    </div>
  )
}

function failureMessage(code: string | null, t: Translate): string {
  if (code === null) {
    return t('job.fail.generic')
  }
  const known: Record<string, Parameters<Translate>[0]> = {
    media_unreadable: 'job.fail.media_unreadable',
    provider_unavailable: 'job.fail.provider_unavailable',
    model_missing: 'job.fail.model_missing',
    out_of_memory: 'job.fail.out_of_memory',
    timeout: 'job.fail.timeout',
    cloud_consent_expired: 'job.fail.cloud_consent_expired',
  }
  return Object.hasOwn(known, code)
    ? t(known[code] ?? 'job.fail.generic')
    : t('job.fail.code', { code })
}

/** Qué está pasando ahora, en una frase. */
function sentence(job: JobView, t: Translate): string | null {
  switch (job.state) {
    case 'FAILED':
    case 'CANCELLED':
      return null
    case 'TRANSCRIBING':
      return typeof job.stage_progress === 'number'
        ? t('job.say.TRANSCRIBING.pct', {
            pct: Math.round(clamp01(job.stage_progress) * 100),
          })
        : t('job.say.TRANSCRIBING')
    case 'DIARIZING':
      return job.transcript_id !== null ? t('job.say.DIARIZING.text') : t('job.say.DIARIZING')
    default:
      return t(`job.say.${job.state}`)
  }
}

export function JobScreen({ job, loading, error, onCancel, onAdjust }: JobScreenProps) {
  const { t } = useI18n()
  const providerId = readString(job?.selection?.provider_id)
  const providers = useCloudProviders(providerId !== null, readString(job?.selection?.model_id))
  const processing = job !== null && (PROCESSABLE_STATES.has(job.state) || job.state === 'CANCELLING')
  const now = useNow(processing)

  if (job === null) {
    return (
      <Panel
        titleId="job-title"
        title={loading ? t('job.title.creating') : t('job.title.none')}
      >
        {error ? (
          <Notice kind="error" title={error} />
        ) : loading ? (
          <div role="status">
            <Busy description={t('job.creating.desc')} />
          </div>
        ) : (
          <p className="voz-field-note">{t('job.empty')}</p>
        )}
      </Panel>
    )
  }

  const cancelling = job.state === 'CANCELLING'
  const percent = Math.round(clamp01(job.progress) * 100)
  const selection = job.selection
  const modelId = readString(selection?.model_id)
  const profileName = readString(selection?.profile?.name)
  const device = readString(selection?.execution?.device)
  const cloudProvider = providers.find((item) => item.id === providerId) ?? null
  const failed = job.state === 'FAILED'
  const completed = job.state === 'COMPLETED'
  const cancelled = job.state === 'CANCELLED'

  const started = parseIso(job.started_at) ?? parseIso(job.created_at)
  const updated = parseIso(job.updated_at)
  const end = processing ? now : (updated ?? now)
  const elapsedSeconds = started === null ? null : Math.max(0, (end - started) / 1000)
  const stageStarted = parseIso(job.stage_started_at)
  const stageSeconds =
    stageStarted === null ? null : Math.max(0, (end - stageStarted) / 1000)
  const etaAt =
    typeof job.eta_seconds === 'number' && updated !== null
      ? updated + job.eta_seconds * 1000
      : null
  const remaining = etaAt === null ? null : (etaAt - now) / 1000

  const say = sentence(job, t)
  const actions = processing ? (
    <Button
      kind="danger--tertiary"
      size="sm"
      renderIcon={StopFilledAlt}
      onClick={onCancel}
      title={t('job.cancel.why')}
      disabled={cancelling || onCancel === undefined}
    >
      {t('job.cancel')}
    </Button>
  ) : (failed || cancelled || completed) && onAdjust ? (
    <Button kind="tertiary" size="sm" onClick={onAdjust} title={t('job.adjust.why')}>
      {t('job.adjust')}
    </Button>
  ) : null

  return (
    <Panel
      className={'voz-job voz-job--' + job.state.toLowerCase()}
      titleId="job-title"
      title={t(`job.state.${job.state}`)}
      actions={actions}
    >
      {cloudProvider !== null ? (
        <div role="note" className="voz-job__cloud">
          <CloudBadge />
          <span>
            {processing
              ? t('job.cloud.running', { provider: cloudProvider.label })
              : t('job.cloud.done', { provider: cloudProvider.label })}
          </span>
        </div>
      ) : null}

      <Stages job={job} t={t} />

      {processing ? (
        <ProgressBar
          label={t('job.progress.total')}
          value={percent}
          max={100}
          helperText={t('job.progress.pct', { pct: percent })}
          {...(cancelling ? { status: 'active' as const } : {})}
        />
      ) : null}

      {say !== null ? (
        <p className="voz-job__say" role="status">
          {say}
        </p>
      ) : null}

      {failed ? <Notice kind="error" title={failureMessage(job.error_code, t)} /> : null}
      {cancelled ? <Notice kind="info" title={t('job.cancelled.note')} /> : null}
      {error ? <Notice kind="error" title={error} /> : null}

      <dl className="voz-figures">
        {elapsedSeconds !== null ? (
          <Figure
            label={processing ? t('job.fig.elapsed') : t('job.fig.total')}
            hint={processing ? 'job.elapsed.hint' : undefined}
          >
            <span className="voz-figure__clock">{formatSeconds(elapsedSeconds)}</span>
          </Figure>
        ) : null}
        {processing ? (
          <Figure label={t('job.fig.remaining')} hint="job.remaining.hint">
            {remaining === null
              ? t('job.remaining.unknown')
              : remaining > 3
                ? t('job.remaining.value', { time: formatSeconds(remaining) })
                : remaining > -5
                  ? t('job.remaining.soon')
                  : t('job.remaining.late')}
          </Figure>
        ) : null}
        {processing && stageSeconds !== null ? (
          <Figure label={t('job.fig.stage')}>
            <span className="voz-figure__clock">{formatSeconds(stageSeconds)}</span>
          </Figure>
        ) : null}
        {modelId ? <Figure label={t('job.fig.model')}>{modelId}</Figure> : null}
        {device ? (
          <Figure label={t('job.fig.device')} hint="job.device.hint">
            <DeviceLabel device={device} />
          </Figure>
        ) : null}
        {profileName ? (
          <Figure label={t('job.fig.profile')}>
            <ProcessingProfileLabel name={profileName} />
          </Figure>
        ) : null}
      </dl>
    </Panel>
  )
}
