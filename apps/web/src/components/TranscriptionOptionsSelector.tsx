import { useCallback, useEffect, useId, useRef, useState } from 'react'

import {
  getTranscriptionOptions,
  type BlockingReason,
  type BlockingReasonCode,
  type ExecutionDecision,
  type ProcessingProfile,
  type TranscriptionOption,
} from '../api/transcriptionOptions'
import { getEstimate, type CloudEstimate } from '../api/providers'
import { compareModelIds } from '../lib/modelOrder'
import { CloudBadge } from './CloudBadge'

export interface TranscriptionOptionsSelectorProps {
  value: string | null
  onChange: (optionId: string | null) => void
  disabled?: boolean
  /** Al cambiar, vuelve a pedir las opciones (p. ej. tras instalar o borrar un modelo). */
  refreshKey?: number
  /** Grabación importada: permite estimar el coste de las opciones cloud. */
  mediaAssetId?: string
  /**
   * S11.09: `true` si el padre puede iniciar (la opción elegida es local, o es
   * cloud y el usuario marcó «Entiendo que el audio sale de mi equipo»).
   * El padre debe bloquear «Transcribir» mientras valga `false`.
   */
  onCloudConsentChange?: (ok: boolean) => void
}

// `cloud` y `provider_label` los añade el backend (docs/api/providers.md) y no
// están en el tipo base.
type CloudAwareOption = TranscriptionOption & {
  cloud?: boolean
  provider_label?: string | null
}

function providerName(option: CloudAwareOption): string {
  return option.provider_label ?? option.provider_id
}

/** `key` identifica la consulta: si no coincide con la actual, sigue cargando. */
type EstimateResult =
  | { key: string; phase: 'error' }
  | { key: string; phase: 'ready'; estimate: CloudEstimate }
type EstimateState = { phase: 'loading' } | EstimateResult

type LoadState =
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; options: CloudAwareOption[] }

const BLOCKING_REASON_LABELS: Record<BlockingReasonCode, string> = {
  model_not_registered: 'Modelo no instalado',
  model_files_missing: 'Faltan archivos del modelo',
  revision_unpinned: 'Revisión no fijada',
  runtime_unavailable: 'Runtime Faster Whisper no instalado',
  execution_unavailable: 'Sin dispositivo compatible',
  transcription_unavailable: 'Transcripción no disponible',
}

const PROFILE_LABELS: Record<string, string> = {
  fast: 'Rápido',
  quality: 'Calidad',
}

const DEVICE_LABELS: Record<string, string> = {
  cuda: 'GPU (CUDA)',
  cpu: 'CPU',
}

function describeBlockingReason(reason: BlockingReason): string {
  return Object.hasOwn(BLOCKING_REASON_LABELS, reason)
    ? BLOCKING_REASON_LABELS[reason as BlockingReasonCode]
    : reason
}

function describeProfile(profile: ProcessingProfile): string {
  return PROFILE_LABELS[profile.name] ?? profile.name
}

function describeExecution(execution: ExecutionDecision): string {
  const device = DEVICE_LABELS[execution.device] ?? execution.device
  const base = device + ' · ' + execution.precision
  return execution.fallback_reason ? base + ' (respaldo)' : base
}

/** Iniciables primero y, dentro de cada grupo, orden fijo del catálogo. */
function sortOptions(options: CloudAwareOption[]): CloudAwareOption[] {
  return [...options].sort(
    (a, b) =>
      Number(b.can_start) - Number(a.can_start) ||
      compareModelIds(a.model_id, b.model_id),
  )
}

function formatEstimate(estimate: CloudEstimate): string {
  return (
    'Costo estimado: ' +
    String(estimate.minutes).replace('.', ',') +
    ' min · ≈ ' +
    estimate.usd.toFixed(2).replace('.', ',') +
    ' USD'
  )
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function toUserMessage(error: unknown): string {
  return error instanceof Error && error.message
    ? error.message
    : 'No se pudieron consultar las opciones de transcripción.'
}

export function TranscriptionOptionsSelector({
  value,
  onChange,
  disabled = false,
  refreshKey = 0,
  mediaAssetId,
  onCloudConsentChange,
}: TranscriptionOptionsSelectorProps) {
  const [state, setState] = useState<LoadState>({ phase: 'loading' })
  // Opción para la que se dio consentimiento: cambiar de opción lo invalida.
  const [consentFor, setConsentFor] = useState<string | null>(null)
  const [estimateResult, setEstimateResult] = useState<EstimateResult | null>(
    null,
  )
  const [attempt, setAttempt] = useState(0)
  const baseId = useId()
  const onChangeRef = useRef(onChange)
  const onConsentRef = useRef(onCloudConsentChange)

  const retry = useCallback(() => {
    setState({ phase: 'loading' })
    setAttempt((current) => current + 1)
  }, [])

  useEffect(() => {
    onChangeRef.current = onChange
    onConsentRef.current = onCloudConsentChange
  }, [onChange, onCloudConsentChange])

  const selected =
    state.phase === 'ready'
      ? state.options.find((option) => option.option_id === value)
      : undefined
  const selectedCloud = selected?.cloud === true ? selected : undefined
  const consentOk = selectedCloud === undefined || consentFor === value
  const cloudProviderId = selectedCloud?.provider_id
  const cloudModelId = selectedCloud?.model_id
  const estimateKey =
    cloudProviderId && mediaAssetId
      ? [cloudProviderId, cloudModelId ?? '', mediaAssetId].join('|')
      : null
  const estimateState: EstimateState =
    estimateResult !== null && estimateResult.key === estimateKey
      ? estimateResult
      : { phase: 'loading' }

  useEffect(() => {
    onConsentRef.current?.(consentOk)
  }, [consentOk])

  // Estimación del costo (no envía nada) al elegir una opción cloud.
  useEffect(() => {
    if (!cloudProviderId || !mediaAssetId || estimateKey === null) {
      return
    }
    const controller = new AbortController()
    void getEstimate(
      cloudProviderId,
      mediaAssetId,
      cloudModelId,
      controller.signal,
    )
      .then((estimate) => {
        setEstimateResult({ key: estimateKey, phase: 'ready', estimate })
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          setEstimateResult({ key: estimateKey, phase: 'error' })
        }
      })
    return () => {
      controller.abort()
    }
  }, [cloudProviderId, cloudModelId, mediaAssetId, estimateKey])

  useEffect(() => {
    const controller = new AbortController()
    void getTranscriptionOptions(controller.signal)
      .then((payload) => {
        setState({ phase: 'ready', options: sortOptions(payload.options) })
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          setState({ phase: 'error', message: toUserMessage(error) })
        }
      })
    return () => {
      controller.abort()
    }
  }, [attempt, refreshKey])

  // Mantiene coherente la selección del padre con el catálogo observado:
  // descarta valores inexistentes o no iniciables y preselecciona la única viable
  // local: una opción cloud jamás se preselecciona.
  useEffect(() => {
    if (state.phase !== 'ready') {
      return
    }
    const startable = state.options.filter((option) => option.can_start)
    if (value !== null) {
      if (!startable.some((option) => option.option_id === value)) {
        onChangeRef.current(null)
      }
      return
    }
    const local = startable.filter((option) => option.cloud !== true)
    const only =
      local.length === 1 && startable.length === 1 ? local[0] : undefined
    if (only) {
      onChangeRef.current(only.option_id)
    }
  }, [state, value])

  return (
    <fieldset className="options-fieldset" disabled={disabled}>
      <legend className="options-legend">Modelo de transcripción</legend>

      {state.phase === 'loading' ? (
        <p className="options-loading" aria-live="polite">
          Consultando los modelos de este equipo…
        </p>
      ) : state.phase === 'error' ? (
        <div className="options-error" role="alert">
          <p>{state.message}</p>
          <button type="button" onClick={retry}>
            Reintentar
          </button>
        </div>
      ) : state.options.length === 0 ? (
        <p className="options-empty">
          No hay opciones de transcripción conocidas.
        </p>
      ) : (
        <>
          <ul className="options-list">
            {state.options.map((option) => {
              const blocked = !option.can_start
              const cloud = option.cloud === true
              const provider = providerName(option)
              const checked = value === option.option_id
              const reasonsId = baseId + '-reasons-' + option.option_id
              const className = [
                'options-item',
                blocked ? 'options-item--blocked' : '',
                checked ? 'options-item--selected' : '',
              ]
                .filter(Boolean)
                .join(' ')
              return (
                <li key={option.option_id} className={className}>
                  <label className="options-label">
                    <input
                      type="radio"
                      name="transcription-option"
                      value={option.option_id}
                      checked={checked}
                      disabled={blocked}
                      aria-describedby={blocked ? reasonsId : undefined}
                      onChange={() => {
                        onChange(option.option_id)
                      }}
                    />
                    <span className="options-body">
                      <span className="options-title">
                        <strong>
                          {option.display_name.trim() || option.model_id}
                        </strong>
                        {cloud ? <CloudBadge /> : null}
                        {!cloud && option.recommendation?.recommended ? (
                          <span className="options-badge">Recomendado</span>
                        ) : null}
                      </span>
                      {cloud ? (
                        <span className="options-meta">
                          <span>Tu audio se enviará a {provider}</span>
                        </span>
                      ) : null}
                      <span className="options-meta">
                        <span>Modelo: {option.model_id}</span>
                        {option.profile ? (
                          <span>Perfil: {describeProfile(option.profile)}</span>
                        ) : null}
                        {option.execution ? (
                          <span>
                            Ejecución: {describeExecution(option.execution)}
                          </span>
                        ) : null}
                      </span>
                      {blocked ? (
                        <span className="options-reasons" id={reasonsId}>
                          {cloud
                            ? 'Sin clave de ' +
                              provider +
                              ': añádela en «Proveedores cloud (opcional)».'
                            : option.blocking_reasons
                                .map(describeBlockingReason)
                                .join(' · ')}
                        </span>
                      ) : null}
                    </span>
                  </label>
                </li>
              )
            })}
          </ul>
          {state.options.every((option) => !option.can_start) ? (
            <p className="options-notice">
              Instala un modelo para transcribir desde la sección «Modelos».
            </p>
          ) : null}
          {selectedCloud ? (
            <div
              className="cloud-warning"
              role="group"
              aria-label="Aviso de envío a la nube"
            >
              <p>
                <CloudBadge /> Tu audio se enviará a{' '}
                <strong>{providerName(selectedCloud)}</strong> y
                saldrá de tu equipo.
              </p>
              {mediaAssetId ? (
                <p className="cloud-warning-estimate" aria-live="polite">
                  {estimateState.phase === 'ready'
                    ? formatEstimate(estimateState.estimate)
                    : estimateState.phase === 'error'
                      ? 'No se pudo estimar el costo.'
                      : 'Estimando el costo…'}
                </p>
              ) : null}
              {estimateState.phase === 'ready' && mediaAssetId ? (
                <p className="cloud-warning-note">
                  Tarifa de referencia del {estimateState.estimate.price_date},
                  no verificada en vivo: tu factura real puede diferir.
                </p>
              ) : null}
              <label>
                <input
                  type="checkbox"
                  checked={consentOk}
                  onChange={(event) => {
                    setConsentFor(event.target.checked ? value : null)
                  }}
                />
                Entiendo que el audio sale de mi equipo
              </label>
            </div>
          ) : null}
        </>
      )}
    </fieldset>
  )
}
