import { useCallback, useEffect, useId, useRef, useState } from 'react'
import {
  Accordion,
  AccordionItem,
  Checkbox,
  Link,
  RadioTile,
  Tag,
  TileGroup,
} from '@carbon/react'

import {
  getTranscriptionOptions,
  type BlockingReason,
  type BlockingReasonCode,
  type TranscriptionOption,
} from '../api/transcriptionOptions'
import { getEstimate, type CloudEstimate } from '../api/providers'
import { localeOf, useI18n, type Translate } from '../i18n/i18n'
import type { MessageKey } from '../i18n/messages'
import { compareModelIds } from '../lib/modelOrder'
import { CloudBadge } from './CloudBadge'
import { Busy } from './Busy'
import { ComputeCapabilitiesLabel, DeviceLabel, PrecisionLabel, ProcessingProfileLabel } from './TechTerms'
import { Term } from './Hint'
import { Notice } from './Notice'
import './TranscriptionOptionsSelector.scss'

export interface TranscriptionOptionsSelectorProps {
  value: string | null
  onChange: (optionId: string | null) => void
  onSelectedOptionChange?: (option: TranscriptionOption | null) => void
  disabled?: boolean
  /** Al cambiar, vuelve a pedir las opciones (p. ej. tras instalar o borrar un modelo). */
  refreshKey?: number
  /** Grabación importada: permite estimar el coste de las opciones cloud. */
  mediaAssetId?: string
  /**
   * S11.09: `true` si el padre puede iniciar (la opción elegida es local, o es
   * cloud y el usuario marcó «Entiendo que el audio sale de mi equipo»).
   * Falla cerrado: sin catálogo listo no se sabe si la opción es local, así que
   * vale `false`. El padre debe bloquear «Transcribir» mientras valga `false`.
   */
  onCloudConsentChange?: (ok: boolean) => void
}

// `cloud` y `provider_label` los añade el backend (docs/api/providers.md) y no
// están en el tipo base.
type CloudAwareOption = TranscriptionOption & {
  cloud?: boolean
  provider_label?: string | null
}

function fallbackMessage(reason: string): MessageKey {
  if (reason === 'cuda_unavailable') return 'opt.fallback.cudaUnavailable'
  if (reason === 'cuda_precision_unsupported') return 'opt.fallback.cudaPrecision'
  return 'opt.fallback.generic'
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
  | { phase: 'error'; message: string | null }
  | { phase: 'ready'; options: CloudAwareOption[] }

const BLOCKING_REASON_LABELS: Record<BlockingReasonCode, MessageKey> = {
  model_not_registered: 'opt.block.model_not_registered',
  model_files_missing: 'opt.block.model_files_missing',
  revision_unpinned: 'opt.block.revision_unpinned',
  runtime_unavailable: 'opt.block.runtime_unavailable',
  execution_unavailable: 'opt.block.execution_unavailable',
  transcription_unavailable: 'opt.block.transcription_unavailable',
}

function describeBlockingReason(reason: BlockingReason, t: Translate): string {
  return Object.hasOwn(BLOCKING_REASON_LABELS, reason)
    ? t(BLOCKING_REASON_LABELS[reason as BlockingReasonCode])
    : reason
}

/** Iniciables primero y, dentro de cada grupo, orden fijo del catálogo. */
function sortOptions(options: CloudAwareOption[]): CloudAwareOption[] {
  return [...options].sort(
    (a, b) =>
      Number(b.can_start) - Number(a.can_start) ||
      compareModelIds(a.model_id, b.model_id),
  )
}

function formatEstimate(estimate: CloudEstimate, t: Translate, lang: 'es' | 'en'): string {
  const locale = localeOf(lang)
  return t('opt.estimate', {
    minutes: estimate.minutes.toLocaleString(locale),
    usd: estimate.usd.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  })
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function TranscriptionOptionsSelector({
  value,
  onChange,
  disabled = false,
  refreshKey = 0,
  mediaAssetId,
  onCloudConsentChange,
  onSelectedOptionChange,
}: TranscriptionOptionsSelectorProps) {
  const { t, tn, lang } = useI18n()
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
  const onSelectedRef = useRef(onSelectedOptionChange)

  const retry = useCallback(() => {
    setState({ phase: 'loading' })
    setAttempt((current) => current + 1)
  }, [])

  useEffect(() => {
    onChangeRef.current = onChange
    onConsentRef.current = onCloudConsentChange
    onSelectedRef.current = onSelectedOptionChange
  }, [onChange, onCloudConsentChange, onSelectedOptionChange])

  const selected =
    state.phase === 'ready'
      ? state.options.find((option) => option.option_id === value)
      : undefined
  const selectedCloud = selected?.cloud === true ? selected : undefined
  useEffect(() => {
    onSelectedRef.current?.(selected ?? null)
  }, [selected])
  // Fail-closed: solo es válido si la opción es conocida (catálogo listo) y es
  // local, o si hay consentimiento explícito para esa opción cloud.
  const consentOk =
    selected !== undefined &&
    (selectedCloud === undefined || consentFor === value)
  const unverified = value !== null && state.phase !== 'ready'
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
          setState({
            phase: 'error',
            message: error instanceof Error && error.message ? error.message : null,
          })
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

  const usable = state.phase === 'ready' ? state.options.filter((o) => o.can_start) : []
  const unavailable =
    state.phase === 'ready' ? state.options.filter((o) => !o.can_start) : []
  const goToModels = () => {
    window.location.hash = 'modelos'
  }

  return (
    <div className="voz-options">
      {unverified ? (
        <Notice kind="warning" title={t('opt.consent.unverified')} />
      ) : null}
      {state.phase === 'loading' ? (
        <div aria-live="polite">
          <Busy description={t('opt.loading')} />
        </div>
      ) : state.phase === 'error' ? (
        <Notice
          kind="error"
          title={t('opt.error.title')}
          subtitle={state.message ?? t('opt.error.generic')}
          action={{ label: t('common.retry'), onClick: retry }}
        />
      ) : state.options.length === 0 ? (
        <Notice kind="info" title={t('opt.none')} />
      ) : (
        <>
          <TileGroup
            name={baseId + '-option'}
            legend={t('opt.legend')}
            valueSelected={value ?? ''}
            disabled={disabled}
            onChange={(selection) => {
              onChange(String(selection))
            }}
          >
            {usable.map((option) => {
              const cloud = option.cloud === true
              const provider = providerName(option)
              const titleId = baseId + '-title-' + option.option_id
              return (
                <RadioTile
                  key={option.option_id}
                  id={baseId + '-tile-' + option.option_id}
                  value={option.option_id}
                  aria-labelledby={titleId}
                >
                  <span className="voz-option">
                    <span className="voz-option__title">
                      <strong id={titleId}>
                        {option.display_name.trim() || option.model_id}
                      </strong>
                      {cloud ? <CloudBadge plain /> : null}
                      {!cloud && option.recommendation?.recommended ? (
                        <Tag type="green" size="sm">
                          <Term definition="opt.recommended.def" plain>{t('opt.recommended')}</Term>
                        </Tag>
                      ) : null}
                    </span>
                    {cloud ? (
                      <span className="voz-option__meta">
                        {t('opt.sendsTo', { provider })}
                      </span>
                    ) : null}
                    <span className="voz-option__meta">
                      <span>
                        {t('opt.model')}: {option.model_id}
                      </span>
                      {!cloud && option.profile ? (
                        <span>
                          <Term definition="opt.profile.def" plain>{t('opt.profile')}</Term>
                          {': '}
                          <ProcessingProfileLabel name={option.profile.name} plain />
                        </span>
                      ) : null}
                      {!cloud && option.execution ? (
                        <span>
                          <Term definition="opt.execution.def" plain>{t('opt.execution')}</Term>
                          {': '}
                          <DeviceLabel device={option.execution.device} plain />
                          {' · '}
                          <PrecisionLabel precision={option.execution.precision} plain />
                          {option.execution.fallback_reason ? (
                            <>
                              {' '}
                              <span>{t(fallbackMessage(option.execution.fallback_reason))}</span>
                            </>
                          ) : null}
                        </span>
                      ) : null}
                    </span>
                    <span className="voz-option__meta">
                      {cloud ? t('opt.devices.remote') : (
                        <ComputeCapabilitiesLabel capabilities={option.capabilities} />
                      )}
                      {!cloud && option.profile?.device_preference === 'gpu_preferred' ? (
                        <span>{t('opt.policy.automatic')}</span>
                      ) : !cloud && option.profile?.device_preference === 'cpu_only' ? (
                        <span>{t('opt.policy.cpu')}</span>
                      ) : null}
                    </span>
                  </span>
                </RadioTile>
              )
            })}
          </TileGroup>
          {usable.length === 0 ? (
            <Notice
              kind="info"
              title={t('opt.installFirst')}
              action={{ label: t('opt.goModels'), onClick: goToModels }}
            />
          ) : null}
          {unavailable.length > 0 ? (
            <Accordion isFlush className="voz-options__unavailable">
              <AccordionItem
                title={tn('opt.unavailable', unavailable.length)}
              >
                <ul className="voz-unavailable">
                  {unavailable.map((option) => {
                    const cloud = option.cloud === true
                    const provider = providerName(option)
                    return (
                      <li key={option.option_id} className="voz-unavailable__item">
                        <span className="voz-option__title">
                          <strong>
                            {option.display_name.trim() || option.model_id}
                          </strong>
                          {cloud ? <CloudBadge /> : null}
                        </span>
                        <span className="voz-option__reasons">
                          {cloud
                            ? t('opt.noKey', { provider })
                            : option.blocking_reasons
                                .map((reason) => describeBlockingReason(reason, t))
                                .join(' · ')}
                        </span>
                        <Link href={cloud ? '#proveedores' : '#modelos'}>
                          {cloud ? t('opt.goProviders') : t('opt.goModels')}
                        </Link>
                      </li>
                    )
                  })}
                </ul>
              </AccordionItem>
            </Accordion>
          ) : null}
          {selectedCloud ? (
            <div role="group" aria-label={t('opt.cloudNotice')}>
              <Notice
                kind="warning"
                title={t('opt.cloudWarning', { provider: providerName(selectedCloud) })}
              >
                <div className="voz-cloud-warning">
                  <CloudBadge plain />
                  {mediaAssetId ? (
                    <p aria-live="polite">
                      {estimateState.phase === 'ready'
                        ? formatEstimate(estimateState.estimate, t, lang)
                        : estimateState.phase === 'error'
                          ? t('opt.estimate.error')
                          : t('opt.estimate.loading')}
                    </p>
                  ) : null}
                  {estimateState.phase === 'ready' && mediaAssetId ? (
                    <p>{t('opt.estimate.note', { date: estimateState.estimate.price_date })}</p>
                  ) : null}
                </div>
              </Notice>
              <Checkbox
                id={baseId + '-consent'}
                labelText={t('opt.consent')}
                checked={consentOk}
                onChange={(_event, { checked }) => {
                  setConsentFor(checked ? value : null)
                }}
              />
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}
