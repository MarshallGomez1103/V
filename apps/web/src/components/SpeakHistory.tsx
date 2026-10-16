import { useEffect, useId, useRef, useState } from 'react'
import { Button } from '@carbon/react'
import { Download, PlayFilledAlt, TrashCan } from '@carbon/icons-react'

import {
  ACTIVE_SYNTHESIS_STATES,
  deleteSynthesis,
  listSynthesis,
  messageForSynthesisError,
  SynthesisApiError,
  synthesisAudioUrl,
  type SynthesisModel,
  type SynthesisView,
} from '../api/synthesis'
import { localeOf, useI18n } from '../i18n/i18n'
import { formatDuration } from '../lib/formatTime'
import { AudioPlayer } from './AudioPlayer'
import { Busy } from './Busy'
import { Notice } from './Notice'
import { Panel } from './Panel'
import './SpeakHistory.scss'

export interface SpeakHistoryProps {
  refreshKey?: string | number
  models?: SynthesisModel[]
  onDeleted?: (id: string) => void
}

type HistoryState =
  | { phase: 'loading' }
  | { phase: 'error'; code: string }
  | { phase: 'ready'; items: SynthesisView[] }

export function SpeakHistory({ refreshKey, models = [], onDeleted }: SpeakHistoryProps) {
  const { t } = useI18n()
  const titleId = useId()
  const historyDescription = useRef<HTMLSpanElement>(null)
  const [state, setState] = useState<HistoryState>({ phase: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void listSynthesis(undefined, controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setState({ phase: 'ready', items })
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({ phase: 'error', code: error instanceof SynthesisApiError ? error.code : '' })
        }
      })
    return () => { controller.abort() }
  }, [refreshKey, attempt])

  const removed = (id: string) => {
    historyDescription.current?.focus()
    setState((current) => current.phase === 'ready'
      ? { ...current, items: current.items.filter((job) => job.id !== id) }
      : current)
    setSelected((current) => current === id ? null : current)
    setAttempt((current) => current + 1)
    onDeleted?.(id)
  }

  return (
    <Panel titleId={titleId} title={t('speak.history.title')}
      description={<span ref={historyDescription} tabIndex={-1}>{t('speak.history.description')}</span>}
      className="voz-speak-history">
      {state.phase === 'loading' ? (
        <div role="status"><Busy description={t('speak.history.loading')} /></div>
      ) : state.phase === 'error' ? (
        <Notice kind="error"
          title={state.code ? messageForSynthesisError(state.code) : t('speak.history.error')}
          action={{ label: t('common.retry'), onClick: () => {
            setState({ phase: 'loading' })
            setAttempt((current) => current + 1)
          } }} />
      ) : state.items.length === 0 ? (
        <p className="voz-field-note">{t('speak.history.empty')}</p>
      ) : (
        <ul className="voz-speak-history__list">
          {state.items.map((job) => {
            const voice = models.find((model) => model.provider_id === job.provider_id
              && model.model_id === job.model_id)?.voices.find((item) => item.id === job.voice_id)
            return (
              <HistoryRow key={job.id} job={job} voiceName={voice?.name || job.voice_id}
                selected={selected === job.id}
                onSelect={() => { setSelected((current) => current === job.id ? null : job.id) }}
                onDeleted={removed} />
            )
          })}
        </ul>
      )}
    </Panel>
  )
}

function HistoryRow({ job, voiceName, selected, onSelect, onDeleted }: {
  job: SynthesisView
  voiceName: string
  selected: boolean
  onSelect: () => void
  onDeleted: (id: string) => void
}) {
  const { t, lang } = useI18n()
  const [confirming, setConfirming] = useState(false)
  const deleteButton = useRef<HTMLButtonElement>(null)
  const restoreDeleteFocus = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const audio = job.state === 'COMPLETED' ? job.audio : null
  const preview = job.text_preview.slice(0, 160)
  const truncated = job.text_length > preview.length || job.text_preview.length > preview.length
  const active = ACTIVE_SYNTHESIS_STATES.has(job.state)

  useEffect(() => {
    if (!confirming && restoreDeleteFocus.current) {
      deleteButton.current?.focus()
      restoreDeleteFocus.current = false
    }
  }, [confirming])

  const remove = () => {
    if (busy || active || !confirming) return
    setBusy(true)
    setError(null)
    void deleteSynthesis(job.id)
      .then(() => { onDeleted(job.id) })
      .catch((caught: unknown) => {
        setError(caught instanceof SynthesisApiError ? caught.code : '')
        setBusy(false)
      })
  }

  return (
    <li className="voz-speak-history__item">
      <p className="voz-speak-history__text">{preview}{truncated ? '…' : ''}</p>
      <dl className="voz-speak-history__facts">
        <div><dt>{t('speak.fig.voice')}</dt><dd>{voiceName}</dd></div>
        <div><dt>{t('speak.fig.duration')}</dt><dd>{audio ? formatDuration(audio.duration_ms) : '—'}</dd></div>
        <div><dt>{t('speak.history.date')}</dt><dd><time dateTime={job.created_at}>
          {new Date(job.created_at).toLocaleString(localeOf(lang), { dateStyle: 'medium', timeStyle: 'short' })}
        </time></dd></div>
      </dl>
      <p className="voz-field-note">{t(`speak.state.${job.state}`)}</p>
      <div className="voz-speak-history__actions">
        {audio ? <>
          <Button kind="tertiary" size="sm" renderIcon={PlayFilledAlt}
            disabled={busy} aria-expanded={selected} onClick={onSelect}>
            {t(selected ? 'speak.history.close' : 'speak.history.play')}
          </Button>
          <Button kind="ghost" size="sm" renderIcon={Download} href={synthesisAudioUrl(job.id, true)}>
            {t('speak.download')}
          </Button>
        </> : null}
        {!active && !confirming ? (
          <Button kind="danger--tertiary" size="sm" renderIcon={TrashCan}
            ref={deleteButton}
            onClick={() => { setConfirming(true) }}>{t('common.delete')}</Button>
        ) : null}
      </div>
      {!active && confirming ? (
        <div className="voz-speak-history__confirmation">
          <p>{t('speak.history.confirm')}</p>
          <div className="voz-speak-history__actions">
            <Button kind="danger" size="sm" disabled={busy} onClick={remove}>
              {t('speak.history.delete')}
            </Button>
            <Button kind="ghost" size="sm" disabled={busy} autoFocus
              onClick={() => {
                restoreDeleteFocus.current = true
                setConfirming(false)
                setError(null)
              }}>{t('common.cancel')}</Button>
          </div>
        </div>
      ) : null}
      {busy ? <div role="status"><Busy description={t('speak.history.deleting')} /></div> : null}
      {error !== null ? <Notice kind="error"
        title={error ? messageForSynthesisError(error) : t('speak.history.deleteError')} /> : null}
      {audio && selected ? <AudioPlayer mediaAssetId={job.id} src={synthesisAudioUrl(job.id)}
        durationMs={audio.duration_ms} seekToMs={0} seekNonce={1} /> : null}
    </li>
  )
}
