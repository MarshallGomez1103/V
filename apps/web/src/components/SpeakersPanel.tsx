import { useEffect, useState } from 'react'
import { Button, IconButton, Modal, Select, SelectItem, Tag, TextInput } from '@carbon/react'
import {
  ArrowDown,
  ArrowUp,
  Filter,
  FilterRemove,
  PlayFilledAlt,
  Renew,
} from '@carbon/icons-react'

import {
  listSpeakers,
  mergeSpeakers,
  updateSpeaker,
  type RediarizeRequest,
  type Speaker,
} from '../api/speakers'
import { isAbortError } from '../api/errors'
import { translate, useI18n } from '../i18n/i18n'
import { formatDuration } from '../lib/formatTime'
import type { Playhead } from '../lib/playhead'
import {
  neighborTurn,
  percentOf,
  pickSample,
  speakerTurns,
  talkMs,
  type Sample,
  type SpeakerSegment,
  type Turn,
} from '../lib/speakerTurns'
import { SpeakerCountPicker } from './DiarizationOptions'

import { Busy } from './Busy'
import { Notice } from './Notice'
import { Panel } from './Panel'
import './SpeakersPanel.scss'

interface SpeakersPanelProps {
  transcriptId: string
  onChanged?: () => void
  /** Los hablantes aún se están calculando: se dice en lugar de «no tiene hablantes». */
  pending?: boolean
  /** Segmentos cargados: dan el tiempo de habla (si el servidor no lo trae), saltos y muestras. */
  segments?: readonly SpeakerSegment[]
  playhead?: Playhead
  /** Hablante por el que se filtra la transcripción (`null` = todos). */
  filterId?: string | null
  onFilter?: (speakerId: string | null) => void
  onJump?: (turn: Turn) => void
  onSample?: (sample: Sample) => void
  /** Cambiarlo recarga la lista (p. ej. al terminar un recálculo). */
  refreshKey?: number
  /** Recálculo de hablantes: estado y arranque. Sin `onRecalculate` no se ofrece. */
  recalc?: { phase: 'idle' | 'running' | 'failed'; pct: number | null; error: string | null }
  onRecalculate?: (speakers: RediarizeRequest) => Promise<void>
  onOpenModels?: () => void
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : translate('err.speaker.action')
}

function without(record: Record<string, string>, key: string) {
  return Object.fromEntries(Object.entries(record).filter(([k]) => k !== key))
}

/** Remonta el cuerpo al cambiar de transcripción: así se reinicia todo su estado. */
export function SpeakersPanel(props: SpeakersPanelProps) {
  return <SpeakersPanelBody key={props.transcriptId} {...props} />
}

function SpeakersPanelBody({
  transcriptId,
  onChanged,
  pending = false,
  segments = [],
  playhead,
  filterId = null,
  onFilter,
  onJump,
  onSample,
  refreshKey = 0,
  recalc,
  onRecalculate,
  onOpenModels,
}: SpeakersPanelProps) {
  const { t, tn } = useI18n()
  const [speakers, setSpeakers] = useState<Speaker[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  // Nombre en edición por hablante y fusión elegida (origen → destino).
  const [names, setNames] = useState<Record<string, string>>({})
  const [source, setSource] = useState('')
  const [target, setTarget] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [recalcOpen, setRecalcOpen] = useState(false)

  async function reload() {
    try {
      setSpeakers(await listSpeakers(transcriptId))
    } catch (caught) {
      setError(messageOf(caught))
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    void listSpeakers(transcriptId, controller.signal)
      .then((items) => {
        setSpeakers(items)
        setError(null)
      })
      .catch((caught: unknown) => {
        if (!isAbortError(caught)) {
          setError(messageOf(caught))
        }
      })
    return () => {
      controller.abort()
    }
  }, [transcriptId, attempt, refreshKey])

  async function save(speaker: Speaker, changes: { name?: string; color?: string }) {
    try {
      const saved = await updateSpeaker(speaker.id, changes)
      setSpeakers((current) =>
        current?.map((item) => (item.id === saved.id ? saved : item)) ?? null,
      )
      setNames((current) => without(current, speaker.id))
      setError(null)
      onChanged?.()
    } catch (caught) {
      setError(messageOf(caught))
      void reload()
    }
  }

  async function merge(from: Speaker, into: Speaker) {
    setConfirming(false)
    try {
      await mergeSpeakers(from.id, into.id)
      setSource('')
      setTarget('')
      setError(null)
      await reload()
      onChanged?.()
    } catch (caught) {
      setError(messageOf(caught))
      void reload()
    }
  }

  function commitName(speaker: Speaker) {
    const draft = names[speaker.id]?.trim()
    if (draft === undefined || draft === speaker.name) {
      setNames((current) => without(current, speaker.id))
      return
    }
    void save(speaker, { name: draft })
  }

  if (speakers === null && error === null) {
    return (
      <Panel titleId="speakers-title" title={t('spk.title')}>
        <div aria-live="polite">
          <Busy description={t('spk.loading')} />
        </div>
      </Panel>
    )
  }

  // Los que no quedaron con ningún segmento no se pueden usar: se cuentan aparte.
  const used = speakers?.filter((speaker) => speaker.segment_count > 0) ?? []
  const unused = (speakers?.length ?? 0) - used.length
  const totalTalk = used.reduce(
    (sum, speaker) => sum + (speaker.talk_ms ?? talkMs(segments, speaker.id)),
    0,
  )
  const from = used.find((item) => item.id === source) ?? used[0]
  const into =
    used.find((item) => item.id === target && item.id !== from?.id) ??
    used.find((item) => item.id !== from?.id)

  return (
    <>
      <Panel titleId="speakers-title" title={t('spk.title')} description={t('spk.description')}>
        {error !== null && (
          <Notice
            kind="error"
            title={error}
            action={{
              label: t('common.retry'),
              onClick: () => {
                setError(null)
                setAttempt((current) => current + 1)
              },
            }}
          />
        )}
        {speakers?.length === 0 && pending ? (
          <div role="status">
            <Busy description={t('spk.pending')} />
          </div>
        ) : speakers?.length === 0 ? (
          <p className="voz-field-note">{t('spk.none')}</p>
        ) : null}
        <ul className="voz-speakers">
          {used.map((speaker) => {
            const talk = speaker.talk_ms ?? talkMs(segments, speaker.id)
            const share = percentOf(talk, totalTalk)
            const filtering = filterId === speaker.id
            const turns = speakerTurns(segments, speaker.id)
            const sample = pickSample(segments, speaker.id)
            const jump = (direction: 1 | -1) => {
              const target = neighborTurn(turns, playhead?.get() ?? -1, direction)
              if (target !== null) {
                onJump?.(target)
              }
            }
            return (
              <li
                key={speaker.id}
                className={'voz-speakers__item' + (filtering ? ' is-filtering' : '')}
              >
                <div className="voz-speakers__line">
                  <input
                    type="color"
                    className="voz-speakers__color"
                    title={t('spk.color', { name: speaker.name })}
                    aria-label={t('spk.color', { name: speaker.name })}
                    value={speaker.color}
                    onChange={(event) => {
                      void save(speaker, { color: event.target.value })
                    }}
                  />
                  <TextInput
                    id={'speaker-name-' + speaker.id}
                    size="md"
                    hideLabel
                    labelText={t('spk.name', { name: speaker.name })}
                    maxLength={80}
                    value={names[speaker.id] ?? speaker.name}
                    onChange={(event) => {
                      setNames({ ...names, [speaker.id]: event.target.value })
                    }}
                    onBlur={() => {
                      commitName(speaker)
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        commitName(speaker)
                      } else if (event.key === 'Escape') {
                        setNames((current) => without(current, speaker.id))
                      }
                    }}
                  />
                  <Tag type="gray" size="md">
                    {tn('spk.segments', speaker.segment_count)}
                  </Tag>
                </div>
                {totalTalk > 0 ? (
                  <div
                    className="voz-speakers__talk"
                    title={t('spk.talk', { name: speaker.name })}
                  >
                    <span
                      className="voz-speakers__bar"
                      role="img"
                      aria-label={t('spk.talk', { name: speaker.name })}
                    >
                      <span
                        className="voz-speakers__barfill"
                        style={{ inlineSize: String(share) + '%', backgroundColor: speaker.color }}
                      />
                    </span>
                    <span className="voz-speakers__time">
                      {t('spk.talk.value', { time: formatDuration(talk), percent: share })}
                    </span>
                  </div>
                ) : null}
                {onFilter ? (
                  <div className="voz-speakers__tools">
                    <IconButton
                      kind={filtering ? 'secondary' : 'ghost'}
                      size="sm"
                      label={filtering ? t('spk.filter.off') : t('spk.filter', { name: speaker.name })}
                      aria-pressed={filtering}
                      onClick={() => {
                        onFilter(filtering ? null : speaker.id)
                      }}
                    >
                      {filtering ? <FilterRemove /> : <Filter />}
                    </IconButton>
                    <IconButton
                      kind="ghost"
                      size="sm"
                      label={t('spk.prev', { name: speaker.name })}
                      disabled={turns.length === 0}
                      onClick={() => {
                        jump(-1)
                      }}
                    >
                      <ArrowUp />
                    </IconButton>
                    <IconButton
                      kind="ghost"
                      size="sm"
                      label={t('spk.next', { name: speaker.name })}
                      disabled={turns.length === 0}
                      onClick={() => {
                        jump(1)
                      }}
                    >
                      <ArrowDown />
                    </IconButton>
                    <IconButton
                      kind="ghost"
                      size="sm"
                      label={t('spk.sample', { name: speaker.name })}
                      disabled={sample === null}
                      onClick={() => {
                        if (sample !== null) {
                          onSample?.(sample)
                        }
                      }}
                    >
                      <PlayFilledAlt />
                    </IconButton>
                  </div>
                ) : null}
              </li>
            )
          })}
        </ul>
        {recalc?.phase === 'running' ? (
          <div role="status">
            <Busy
              description={
                recalc.pct === null
                  ? t('spk.recalc.running')
                  : t('spk.recalc.progress', { pct: recalc.pct })
              }
            />
          </div>
        ) : null}
        {recalc?.phase === 'failed' ? (
          <Notice
            kind="error"
            title={t('spk.recalc.failed')}
            {...(recalc.error ? { subtitle: recalc.error } : {})}
          />
        ) : null}
        {onRecalculate ? (
          <Button
            kind="tertiary"
            size="md"
            renderIcon={Renew}
            disabled={recalc?.phase === 'running' || pending}
            onClick={() => {
              setRecalcOpen(true)
            }}
          >
            {t('spk.recalc')}
          </Button>
        ) : null}
        {unused > 0 ? (
          <p className="voz-field-note">{tn('spk.unused', unused)}</p>
        ) : null}
        {used.length > 1 && from && into ? (
          <fieldset className="voz-speakers__merge">
            <legend className="cds--label">{t('spk.merge.legend')}</legend>
            <Select
              id="speaker-merge-from"
              size="md"
              labelText={t('spk.merge.from')}
              value={from.id}
              onChange={(event) => {
                setSource(event.target.value)
              }}
            >
              {used.map((item) => (
                <SelectItem key={item.id} value={item.id} text={item.name} />
              ))}
            </Select>
            <Select
              id="speaker-merge-into"
              size="md"
              labelText={t('spk.merge.into')}
              value={into.id}
              onChange={(event) => {
                setTarget(event.target.value)
              }}
            >
              {used
                .filter((item) => item.id !== from.id)
                .map((item) => (
                  <SelectItem key={item.id} value={item.id} text={item.name} />
                ))}
            </Select>
            <Button
              kind="tertiary"
              size="md"
              onClick={() => {
                setConfirming(true)
              }}
            >
              {t('spk.merge')}
            </Button>
          </fieldset>
        ) : null}
      </Panel>
      {recalcOpen && onRecalculate ? (
        <RecalcDialog
          onClose={() => {
            setRecalcOpen(false)
          }}
          onRun={onRecalculate}
          onOpenModels={onOpenModels}
        />
      ) : null}
      {confirming && from && into ? (
        <Modal
          open
          danger
          size="xs"
          closeButtonLabel={t('common.close')}
          modalHeading={t('spk.merge.title')}
          primaryButtonText={t('spk.merge.confirm')}
          secondaryButtonText={t('common.cancel')}
          onRequestClose={() => {
            setConfirming(false)
          }}
          onRequestSubmit={() => {
            void merge(from, into)
          }}
        >
          <p>{t('spk.merge.body', { from: from.name, to: into.name })}</p>
        </Modal>
      ) : null}
    </>
  )
}

interface RecalcDialogProps {
  onClose: () => void
  onRun: (speakers: RediarizeRequest) => Promise<void>
  onOpenModels: (() => void) | undefined
}

/** Pide cuántos hablantes hay (exacto, rango o automático) y lanza el recálculo. */
function RecalcDialog({ onClose, onRun, onOpenModels }: RecalcDialogProps) {
  const { t } = useI18n()
  const [speakers, setSpeakers] = useState<RediarizeRequest>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<{ message: string; missing: boolean } | null>(null)

  async function run() {
    setBusy(true)
    setError(null)
    try {
      await onRun(speakers)
      onClose()
    } catch (caught) {
      setError({
        message: messageOf(caught),
        missing:
          typeof caught === 'object' &&
          caught !== null &&
          'code' in caught &&
          caught.code === 'diarization_models_missing',
      })
      setBusy(false)
    }
  }

  return (
    <Modal
      open
      size="sm"
      closeButtonLabel={t('common.close')}
      modalHeading={t('spk.recalc.title')}
      primaryButtonText={t('spk.recalc.run')}
      secondaryButtonText={t('common.cancel')}
      primaryButtonDisabled={busy}
      onRequestClose={onClose}
      onRequestSubmit={() => {
        void run()
      }}
    >
      <div className="voz-speakers__recalc">
        <p>{t('spk.recalc.body')}</p>
        <SpeakerCountPicker value={speakers} onChange={setSpeakers} disabled={busy} />
        <p className="voz-field-note">{t('spk.recalc.hint')}</p>
        {error ? (
          <Notice
            kind="error"
            title={t('spk.recalc.error')}
            subtitle={error.message}
            {...(error.missing && onOpenModels
              ? { action: { label: t('spk.recalc.models'), onClick: onOpenModels } }
              : {})}
          />
        ) : null}
      </div>
    </Modal>
  )
}
