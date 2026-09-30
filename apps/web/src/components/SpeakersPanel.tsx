import { useEffect, useState } from 'react'

import {
  listSpeakers,
  mergeSpeakers,
  updateSpeaker,
  type Speaker,
} from '../api/speakers'
import { isAbortError } from '../api/errors'

import './SpeakersPanel.css'

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
      <section className="speakers-panel" aria-label="Hablantes">
        <p>Cargando hablantes…</p>
      </section>
    )
  }

  return (
    <section className="speakers-panel" aria-label="Hablantes">
      <h3 className="speakers-panel-title">Hablantes</h3>
      {error !== null && (
        <p className="speakers-panel-error" role="alert">
          {error}
        </p>
      )}
      {speakers?.length === 0 && <p>Esta transcripción no tiene hablantes.</p>}
      <ul className="speakers-panel-list">
        {speakers?.map((speaker) => {
          const others = speakers.filter((item) => item.id !== speaker.id)
          const target = mergeTargets[speaker.id] ?? others[0]?.id ?? ''
          const targetSpeaker = others.find((item) => item.id === target)
          return (
            <li key={speaker.id} className="speakers-panel-item">
              <input
                type="color"
                aria-label={'Color de ' + speaker.name}
                value={speaker.color}
                onChange={(event) => {
                  void save(speaker, { color: event.target.value })
                }}
              />
              <input
                type="text"
                className="speakers-panel-name"
                aria-label={'Nombre de ' + speaker.name}
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
              <span className="speakers-panel-count">
                {speaker.segment_count === 1
                  ? '1 segmento'
                  : speaker.segment_count + ' segmentos'}
              </span>
              {others.length > 0 && (
                <span className="speakers-panel-merge">
                  <select
                    aria-label={'Fusionar ' + speaker.name + ' en'}
                    value={target}
                    onChange={(event) => {
                      setConfirming(null)
                      setMergeTargets({
                        ...mergeTargets,
                        [speaker.id]: event.target.value,
                      })
                    }}
                  >
                    {others.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                  {confirming === speaker.id && targetSpeaker ? (
                    <span role="group" aria-label="Confirmar fusión">
                      <span>
                        {'¿Fusionar «' +
                          speaker.name +
                          '» en «' +
                          targetSpeaker.name +
                          '»?'}
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          void merge(speaker, target)
                        }}
                      >
                        Sí, fusionar
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setConfirming(null)
                        }}
                      >
                        Cancelar
                      </button>
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        setConfirming(speaker.id)
                      }}
                    >
                      Fusionar
                    </button>
                  )}
                </span>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
