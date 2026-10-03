import { Button, ProgressBar, ProgressIndicator, ProgressStep } from '@carbon/react'
import { StopFilledAlt } from '@carbon/icons-react'

import {
  PROCESSABLE_STATES,
  type JobState,
  type JobView,
} from '../api/jobs'
import { useCloudProviders } from '../hooks/useCloudProviders'
import { CloudBadge } from './CloudBadge'
import { Busy } from './Busy'
import { Notice } from './Notice'
import { Panel } from './Panel'
import './JobScreen.scss'

interface JobScreenProps {
  job: JobView | null
  loading?: boolean
  error?: string | null
  onCancel?: () => void
}

// S5.05: cuatro fases visuales; cada estado del backend cae en una de ellas.
const PHASES = [
  'En cola',
  'Preparando audio',
  'Transcribiendo',
  'Resultado',
] as const

type PhaseIndex = 0 | 1 | 2 | 3

const STATE_PHASE: Record<JobState, PhaseIndex> = {
  QUEUED: 0,
  PROBING: 1,
  PREPROCESSING: 1,
  TRANSCRIBING: 2,
  ALIGNING: 2,
  DIARIZING: 2,
  MERGING: 2,
  PERSISTING: 2,
  COMPLETED: 3,
  FAILED: 3,
  CANCELLING: 3,
  CANCELLED: 3,
}

const STATE_LABELS: Record<JobState, string> = {
  QUEUED: 'En cola, esperando turno',
  PROBING: 'Analizando el archivo',
  PREPROCESSING: 'Preparando el audio',
  TRANSCRIBING: 'Transcribiendo el audio',
  ALIGNING: 'Alineando palabras',
  DIARIZING: 'Identificando hablantes',
  MERGING: 'Uniendo resultados',
  PERSISTING: 'Guardando la transcripción',
  COMPLETED: 'Transcripción completada',
  FAILED: 'La transcripción falló',
  CANCELLING: 'Cancelando la transcripción',
  CANCELLED: 'Transcripción cancelada',
}

const FAILURE_MESSAGES: Record<string, string> = {
  media_unreadable: 'No se pudo leer la grabación.',
  provider_unavailable: 'El motor de transcripción no está disponible.',
  model_missing: 'El modelo elegido no está instalado en este equipo.',
  out_of_memory: 'El equipo se quedó sin memoria durante la transcripción.',
  timeout: 'La transcripción tardó demasiado y se detuvo.',
}

function failureMessage(code: string | null): string {
  if (code === null) {
    return 'La transcripción falló.'
  }
  return FAILURE_MESSAGES[code] ?? 'La transcripción falló (código ' + code + ').'
}

function readString(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null
}

const STEP_LABELS: Record<string, string> = {
  'carbon.progress-step.complete': 'Completada',
  'carbon.progress-step.incomplete': 'Pendiente',
  'carbon.progress-step.current': 'En curso',
  'carbon.progress-step.invalid': 'Con error',
}

// Las etapas solo informan: fuera del orden de tabulación.
const INERT_STEP = { tabIndex: -1 }

function stepLabel(id: string): string {
  return STEP_LABELS[id] ?? id
}

export function JobScreen({ job, loading, error, onCancel }: JobScreenProps) {
  const providerId = readString(job?.selection?.provider_id)
  const providers = useCloudProviders(providerId !== null)
  if (job === null) {
    return (
      <Panel
        titleId="job-title"
        title={loading ? 'Creando la transcripción…' : 'Sin transcripción'}
      >
        {error ? (
          <Notice kind="error" title={error} />
        ) : loading ? (
          <div role="status">
            <Busy description="Enviando la grabación al motor local…" />
          </div>
        ) : (
          <p className="voz-field-note">
            Elige una grabación y una opción para empezar.
          </p>
        )}
      </Panel>
    )
  }

  const phase = STATE_PHASE[job.state]
  const processable = PROCESSABLE_STATES.has(job.state)
  const cancelling = job.state === 'CANCELLING'
  const showProgress = processable || cancelling
  const percent = Math.round(Math.min(Math.max(job.progress, 0), 1) * 100)
  const selection = job.selection
  const modelId = readString(selection?.model_id)
  const profileName = readString(selection?.profile?.name)
  const device = readString(selection?.execution?.device)
  const cloudProvider = providers.find((item) => item.id === providerId) ?? null
  const hasSelection = modelId !== null || profileName !== null || device !== null
  const failed = job.state === 'FAILED'
  const completed = job.state === 'COMPLETED'

  return (
    <Panel
      className={'voz-job voz-job--' + job.state.toLowerCase()}
      titleId="job-title"
      title={STATE_LABELS[job.state]}
      actions={
        showProgress ? (
          <Button
            kind="danger--tertiary"
            size="sm"
            renderIcon={StopFilledAlt}
            onClick={onCancel}
            disabled={cancelling || onCancel === undefined}
          >
            Cancelar
          </Button>
        ) : null
      }
    >
      {cloudProvider !== null ? (
        <div role="note" className="voz-job__cloud">
          <CloudBadge />
          <span>
            {showProgress
              ? 'Tu audio se envía a ' +
                cloudProvider.label +
                ' mientras dura esta transcripción.'
              : 'Esta transcripción usó ' +
                cloudProvider.label +
                ' (cloud): tu audio salió de tu equipo.'}
          </span>
        </div>
      ) : null}

      <ProgressIndicator
        aria-label="Etapas"
        currentIndex={phase}
        spaceEqually
        className="voz-job__steps"
      >
        {PHASES.map((label, index) => (
          <ProgressStep
            key={label}
            label={label}
            translateWithId={stepLabel}
            {...INERT_STEP}
            complete={completed}
            invalid={failed && index === 3}
            {...(index === phase ? { 'aria-current': 'step' as const } : {})}
          />
        ))}
      </ProgressIndicator>

      {showProgress ? (
        <ProgressBar
          label="Progreso"
          value={percent}
          max={100}
          helperText={percent + ' %'}
          {...(cancelling ? { status: 'active' as const } : {})}
        />
      ) : null}

      {failed ? <Notice kind="error" title={failureMessage(job.error_code)} /> : null}

      {job.state === 'CANCELLED' ? (
        <Notice
          kind="info"
          title="Cancelaste esta transcripción. La grabación original sigue intacta."
        />
      ) : null}

      {error ? <Notice kind="error" title={error} /> : null}

      {hasSelection ? (
        <dl className="voz-meta">
          {modelId ? (
            <div>
              <dt>Modelo</dt>
              <dd>{modelId}</dd>
            </div>
          ) : null}
          {profileName ? (
            <div>
              <dt>Perfil</dt>
              <dd>{profileName}</dd>
            </div>
          ) : null}
          {device ? (
            <div>
              <dt>Dispositivo</dt>
              <dd>{device}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}
    </Panel>
  )
}
