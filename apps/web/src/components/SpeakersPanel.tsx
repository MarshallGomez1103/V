import { useEffect, useState } from 'react'
import { Button, Modal, Select, SelectItem, Tag, TextInput } from '@carbon/react'

import {
  listSpeakers,
  mergeSpeakers,
  updateSpeaker,
  type Speaker,
} from '../api/speakers'
import { isAbortError } from '../api/errors'
import { translate, useI18n } from '../i18n/i18n'

import { Busy } from './Busy'
import { Notice } from './Notice'
import { Panel } from './Panel'
import './SpeakersPanel.scss'

interface SpeakersPanelProps {
  transcriptId: string
  onChanged?: () => void
  /** Los hablantes aún se están calculando: se dice en lugar de «no tiene hablantes». */
  pending?: boolean
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

function SpeakersPanelBody({ transcriptId, onChanged, pending = false }: SpeakersPanelProps) {
  const { t, tn } = useI18n()
  const [speakers, setSpeakers] = useState<Speaker[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  // Nombre en edición por hablante y fusión elegida (origen → destino).
  const [names, setNames] = useState<Record<string, string>>({})
  const [source, setSource] = useState('')
  const [target, setTarget] = useState('')
  const [confirming, setConfirming] = useState(false)

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
  }, [transcriptId, attempt])

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
          {used.map((speaker) => (
            <li key={speaker.id} className="voz-speakers__item">
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
            </li>
          ))}
        </ul>
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
