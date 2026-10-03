import { useEffect, useState } from 'react'
import { Button, Modal, Select, SelectItem, Tag, TextInput } from '@carbon/react'

import {
  listSpeakers,
  mergeSpeakers,
  updateSpeaker,
  type Speaker,
} from '../api/speakers'
import { isAbortError } from '../api/errors'

import { Busy } from './Busy'
import { Notice } from './Notice'
import { Panel } from './Panel'
import './SpeakersPanel.scss'

interface SpeakersPanelProps {
  transcriptId: string
  onChanged?: () => void
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'No se pudo completar la acción.'
}

function without(record: Record<string, string>, key: string) {
  return Object.fromEntries(Object.entries(record).filter(([k]) => k !== key))
}

/** Remonta el cuerpo al cambiar de transcripción: así se reinicia todo su estado. */
export function SpeakersPanel(props: SpeakersPanelProps) {
  return <SpeakersPanelBody key={props.transcriptId} {...props} />
}

function SpeakersPanelBody({ transcriptId, onChanged }: SpeakersPanelProps) {
  const [speakers, setSpeakers] = useState<Speaker[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Nombre en edición por hablante y fusión pendiente de confirmar.
  const [names, setNames] = useState<Record<string, string>>({})
  const [mergeTargets, setMergeTargets] = useState<Record<string, string>>({})
  const [confirming, setConfirming] = useState<string | null>(null)

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
      .then(setSpeakers)
      .catch((caught: unknown) => {
        if (!isAbortError(caught)) {
          setError(messageOf(caught))
        }
      })
    return () => {
      controller.abort()
    }
  }, [transcriptId])

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

  async function merge(source: Speaker, into: string) {
    setConfirming(null)
    try {
      await mergeSpeakers(source.id, into)
      setMergeTargets((current) => without(current, source.id))
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
      <Panel titleId="speakers-title" title="Hablantes">
        <div aria-live="polite">
          <Busy description="Cargando hablantes…" />
        </div>
      </Panel>
    )
  }

  const targetFor = (speaker: Speaker): Speaker | undefined => {
    const others = speakers?.filter((item) => item.id !== speaker.id) ?? []
    return others.find((item) => item.id === mergeTargets[speaker.id]) ?? others[0]
  }
  const mergeSource = speakers?.find((item) => item.id === confirming)
  const mergeTarget = mergeSource ? targetFor(mergeSource) : undefined

  return (
    <>
      <Panel titleId="speakers-title" title="Hablantes">
        {error !== null && <Notice kind="error" title={error} />}
        {speakers?.length === 0 && (
          <p className="voz-field-note">Esta transcripción no tiene hablantes.</p>
        )}
        <ul className="voz-speakers">
          {speakers?.map((speaker) => {
            const others = speakers.filter((item) => item.id !== speaker.id)
            const target = targetFor(speaker)?.id ?? ''
            return (
              <li key={speaker.id} className="voz-speakers__item">
                <input
                  type="color"
                  className="voz-speakers__color"
                  aria-label={'Color de ' + speaker.name}
                  value={speaker.color}
                  onChange={(event) => {
                    void save(speaker, { color: event.target.value })
                  }}
                />
                <TextInput
                  id={'speaker-name-' + speaker.id}
                  size="md"
                  hideLabel
                  labelText={'Nombre de ' + speaker.name}
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
                  {speaker.segment_count === 1
                    ? '1 segmento'
                    : speaker.segment_count + ' segmentos'}
                </Tag>
                {others.length > 0 && (
                  <div className="voz-speakers__merge">
                    <Select
                      id={'speaker-merge-' + speaker.id}
                      size="md"
                      hideLabel
                      labelText={'Fusionar ' + speaker.name + ' en'}
                      value={target}
                      onChange={(event) => {
                        setMergeTargets({
                          ...mergeTargets,
                          [speaker.id]: event.target.value,
                        })
                      }}
                    >
                      {others.map((item) => (
                        <SelectItem key={item.id} value={item.id} text={item.name} />
                      ))}
                    </Select>
                    <Button
                      kind="tertiary"
                      size="md"
                      onClick={() => {
                        setConfirming(speaker.id)
                      }}
                    >
                      Fusionar
                    </Button>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      </Panel>
      {mergeSource && mergeTarget ? (
        <Modal
          open
          danger
          size="xs"
          closeButtonLabel="Cerrar"
          modalHeading="Fusionar hablantes"
          primaryButtonText="Sí, fusionar"
          secondaryButtonText="Cancelar"
          onRequestClose={() => {
            setConfirming(null)
          }}
          onRequestSubmit={() => {
            void merge(mergeSource, mergeTarget.id)
          }}
        >
          <p>
            {'¿Fusionar «' +
              mergeSource.name +
              '» en «' +
              mergeTarget.name +
              '»? Sus segmentos pasarán al hablante de destino.'}
          </p>
        </Modal>
      ) : null}
    </>
  )
}
