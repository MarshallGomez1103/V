import { useCallback, useEffect, useId, useRef, useState } from 'react'

import {
  getTranscriptionOptions,
  type BlockingReason,
  type BlockingReasonCode,
  type ExecutionDecision,
  type ProcessingProfile,
  type TranscriptionOption,
} from '../api/transcriptionOptions'

export interface TranscriptionOptionsSelectorProps {
  value: string | null
  onChange: (optionId: string | null) => void
  disabled?: boolean
}

type LoadState =
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; options: TranscriptionOption[] }

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
}: TranscriptionOptionsSelectorProps) {
  const [state, setState] = useState<LoadState>({ phase: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const baseId = useId()
  const onChangeRef = useRef(onChange)

  const retry = useCallback(() => {
    setState({ phase: 'loading' })
    setAttempt((current) => current + 1)
  }, [])

  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  useEffect(() => {
    const controller = new AbortController()
    void getTranscriptionOptions(controller.signal)
      .then((payload) => {
        setState({ phase: 'ready', options: payload.options })
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          setState({ phase: 'error', message: toUserMessage(error) })
        }
      })
    return () => {
      controller.abort()
    }
  }, [attempt])

  // Mantiene coherente la selección del padre con el catálogo observado:
  // descarta valores inexistentes o no iniciables y preselecciona la única viable.
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
    const only = startable.length === 1 ? startable[0] : undefined
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
                        {option.recommendation?.recommended ? (
                          <span className="options-badge">Recomendado</span>
                        ) : null}
                      </span>
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
                          {option.blocking_reasons
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
              Instala un modelo para transcribir (Model Manager llegará en una
              sección posterior).
            </p>
          ) : null}
        </>
      )}
    </fieldset>
  )
}
