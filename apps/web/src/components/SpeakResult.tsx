import { Button, ProgressBar } from '@carbon/react'
import { Download, StopFilledAlt } from '@carbon/icons-react'

import {
  ACTIVE_SYNTHESIS_STATES,
  messageForSynthesisError,
  synthesisAudioUrl,
  type SynthesisView,
} from '../api/synthesis'
import { localeOf, useI18n } from '../i18n/i18n'
import { formatDuration } from '../lib/formatTime'
import { AudioPlayer } from './AudioPlayer'
import { Busy } from './Busy'
import { CloudBadge } from './CloudBadge'
import { Notice } from './Notice'
import { Panel } from './Panel'
import './SpeakResult.scss'

interface SpeakResultProps {
  /** `null` mientras la API todavía no devolvió el trabajo recién enviado. */
  job: SynthesisView | null
  reused: boolean
  /** Nombre de la voz con la que se pidió (la API solo devuelve su id). */
  voiceName: string
  locality?: string
  /** Fallo del stream de eventos (conexión), ya traducido. */
  streamError: string | null
  onCancel: () => void
  onReconnect: () => void
}

const clamp01 = (value: number) => Math.min(1, Math.max(0, value))

/** Resultado de una generación: progreso en vivo, cancelación y, al terminar, reproductor y descarga. */
export function SpeakResult({ job, reused, voiceName, locality, streamError, onCancel, onReconnect }: SpeakResultProps) {
  const { t, lang } = useI18n()
  const cloudNotice = locality === 'cloud' ? (
    <Notice kind="warning" title={t('speak.cloud.title')} subtitle={t('speak.cloud.result')}>
      <CloudBadge plain />
    </Notice>
  ) : null
  if (job === null) {
    return (
      <Panel titleId="voz-speak-result" title={t('speak.result.title')} className="voz-speak-result">
        {cloudNotice}
        <div role="status">
          <Busy description={t('speak.generate.creating')} />
        </div>
      </Panel>
    )
  }
  const active = ACTIVE_SYNTHESIS_STATES.has(job.state)
  const cancelling = job.state === 'CANCELLING'
  const cancellable = active && !cancelling
  const percent = Math.round(clamp01(job.progress) * 100)
  const number = new Intl.NumberFormat(localeOf(lang), { maximumFractionDigits: 2 })
  const audio = job.audio

  const actions = cancellable ? (
    <Button
      kind="danger--tertiary"
      size="sm"
      renderIcon={StopFilledAlt}
      onClick={onCancel}
      title={t('speak.cancel.why')}
    >
      {t('speak.cancel')}
    </Button>
  ) : audio ? (
    <Button
      kind="tertiary"
      size="sm"
      renderIcon={Download}
      href={synthesisAudioUrl(job.id, true)}
    >
      {t('speak.download')}
    </Button>
  ) : null

  return (
    <Panel
      titleId="voz-speak-result"
      title={t(`speak.state.${job.state}`)}
      actions={actions}
      className={'voz-speak-result voz-speak-result--' + job.state.toLowerCase()}
    >
      {cloudNotice}
      {reused ? (
        <Notice kind="info" title={t('speak.reused')} subtitle={t('speak.reused.body')} />
      ) : null}

      {active ? (
        <ProgressBar
          label={t('speak.progress.label')}
          max={100}
          {...(job.state === 'QUEUED' ? {} : { value: percent })}
          helperText={
            job.state === 'QUEUED'
              ? t('speak.state.QUEUED')
              : job.chunks_total > 0
                ? t('speak.progress.chunks', {
                    done: job.chunks_done,
                    total: job.chunks_total,
                    pct: percent,
                  })
                : t('speak.progress.pct', { pct: percent })
          }
        />
      ) : null}

      {job.state === 'FAILED' || job.state === 'CANCELLED' ? null : (
        <p className="voz-speak-result__say" role="status">
          {t(`speak.say.${job.state}`)}
        </p>
      )}

      {job.state === 'FAILED' ? (
        <Notice
          kind="error"
          title={t('speak.state.FAILED')}
          subtitle={messageForSynthesisError(job.error_code ?? 'synthesis_failed')}
        />
      ) : null}
      {job.state === 'CANCELLED' ? <Notice kind="info" title={t('speak.say.CANCELLED')} /> : null}
      {streamError !== null && active ? (
        <Notice
          kind="warning"
          title={streamError}
          action={{ label: t('speak.events.retry'), onClick: onReconnect }}
        />
      ) : null}

      {audio ? (
        <>
          <AudioPlayer
            key={job.id}
            mediaAssetId={job.id}
            src={synthesisAudioUrl(job.id)}
            seekToMs={null}
            seekNonce={0}
            durationMs={audio.duration_ms}
          />
          <dl className="voz-speak-figures">
            <Figure label={t('speak.fig.duration')}>{formatDuration(audio.duration_ms)}</Figure>
            <Figure label={t('speak.fig.voice')}>{voiceName}</Figure>
            <Figure label={t('speak.fig.speed')}>
              {t('speak.voice.speedValue', { speed: number.format(job.speed) })}
            </Figure>
            <Figure label={t('speak.fig.rate')}>
              {t('speak.fig.rateValue', { khz: number.format(audio.sample_rate / 1000) })}
            </Figure>
            <Figure label={t('speak.fig.size')}>
              {t('speak.fig.sizeValue', { mb: number.format(audio.size_bytes / 1_048_576) })}
            </Figure>
          </dl>
        </>
      ) : null}
    </Panel>
  )
}

function Figure({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="voz-speak-figure">
      <dt className="voz-speak-figure__label">{label}</dt>
      <dd className="voz-speak-figure__value">{children}</dd>
    </div>
  )
}
