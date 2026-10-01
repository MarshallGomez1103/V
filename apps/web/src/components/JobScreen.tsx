import {
  PROCESSABLE_STATES,
  type JobState,
  type JobView,
} from '../api/jobs'
import { useCloudProviders } from '../hooks/useCloudProviders'
import { CloudBadge } from './CloudBadge'

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

export function JobScreen({ job, loading, error, onCancel }: JobScreenProps) {
  const providerId = readString(job?.selection?.provider_id)
  const providers = useCloudProviders(providerId !== null)
  if (job === null) {
    return (
      <article className="job-card" aria-labelledby="job-title">
        <div className="card-heading">
          <div>
            <p className="section-kicker">TRANSCRIPCIÓN</p>
            <h2 id="job-title">
              {loading ? 'Creando la transcripción…' : 'Sin transcripción'}
            </h2>
          </div>
        </div>
        {error ? (
          <p className="job-error" role="alert">
            {error}
          </p>
        ) : loading ? (
          <p className="empty-state" role="status">
            Enviando la grabación al motor local…
          </p>
        ) : (
          <p className="empty-state">
            Elige una grabación y una opción para empezar.
          </p>
        )}
      </article>
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

  return (
    <article
      className={'job-card job-card--' + job.state.toLowerCase()}
      aria-labelledby="job-title"
    >
      <div className="card-heading">
        <div>
          <p className="section-kicker">TRANSCRIPCIÓN</p>
          <h2 id="job-title">{STATE_LABELS[job.state]}</h2>
        </div>
        {showProgress ? (
          <button
            type="button"
            className="job-cancel"
            onClick={onCancel}
            disabled={cancelling || onCancel === undefined}
          >
            Cancelar
          </button>
        ) : null}
      </div>

      {cloudProvider !== null ? (
        <p className="cloud-privacy" role="note">
          <CloudBadge />
          {showProgress
            ? 'Tu audio se envía a ' +
              cloudProvider.label +
              ' mientras dura esta transcripción.'
            : 'Esta transcripción usó ' +
              cloudProvider.label +
              ' (cloud): tu audio salió de tu equipo.'}
        </p>
      ) : null}

      <ol className="job-stepper" aria-label="Etapas">
        {PHASES.map((label, index) => (
          <li
            key={label}
            className={
              index < phase
                ? 'is-done'
                : index === phase
                  ? 'is-current'
                  : 'is-pending'
            }
            {...(index === phase ? { 'aria-current': 'step' as const } : {})}
          >
            {label}
          </li>
        ))}
      </ol>

      {showProgress ? (
        <div className="job-progress" aria-live="polite">
          <progress value={job.progress} max={1} aria-label="Progreso" />
          <span className="job-percent">{percent + ' %'}</span>
        </div>
      ) : null}

      {job.state === 'FAILED' ? (
        <p className="job-error" role="alert">
          {failureMessage(job.error_code)}
        </p>
      ) : null}

      {job.state === 'CANCELLED' ? (
        <p className="job-notice" role="status">
          Cancelaste esta transcripción. La grabación original sigue intacta.
        </p>
      ) : null}

      {error ? (
        <p className="job-error" role="alert">
          {error}
        </p>
      ) : null}

      {hasSelection ? (
        <dl className="job-selection">
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
    </article>
  )
}
