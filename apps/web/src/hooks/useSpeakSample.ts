import { useCallback, useEffect, useRef, useState } from 'react'

import {
  cancelSynthesis,
  createSynthesis,
  messageForSynthesisError,
  SynthesisApiError,
  synthesisAudioUrl,
  type CreateSynthesisInput,
  type SynthesisView,
} from '../api/synthesis'
import { translate } from '../i18n/i18n'
import { useSynthesisEvents } from './useSynthesisEvents'

export type SamplePhase = 'idle' | 'preparing' | 'playing'

export interface SpeakSample {
  phase: SamplePhase
  /** Mensaje traducido del último fallo (de la API, del trabajo o del navegador). */
  error: string | null
  start: (input: CreateSynthesisInput) => void
  /** Cancela la preparación o detiene la reproducción. */
  stop: () => void
}

/**
 * Muestra corta: crea una síntesis, sigue su progreso y la reproduce al terminar.
 * Un resultado reutilizado puede ser de otro trabajo (p. ej. la generación del mismo
 * texto), así que solo se cancelan los trabajos que esta muestra creó.
 */
export function useSpeakSample(): SpeakSample {
  const [jobId, setJobId] = useState<string | null>(null)
  const [seed, setSeed] = useState<SynthesisView | null>(null)
  const [creating, setCreating] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const events = useSynthesisEvents(jobId)
  const job = events.job ?? (seed?.id === jobId ? seed : null)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const ownedRef = useRef<string | null>(null)
  const tokenRef = useRef(0)

  const release = useCallback(() => {
    tokenRef.current += 1
    const audio = audioRef.current
    audioRef.current = null
    audio?.pause()
    const owned = ownedRef.current
    ownedRef.current = null
    if (owned !== null) {
      cancelSynthesis(owned).catch(() => undefined)
    }
    setJobId(null)
    setSeed(null)
    setCreating(false)
    setPlaying(false)
  }, [])

  const finish = useCallback(() => {
    audioRef.current = null
    ownedRef.current = null
    setJobId(null)
    setSeed(null)
    setPlaying(false)
  }, [])

  const start = useCallback(
    (input: CreateSynthesisInput) => {
      release()
      setError(null)
      setCreating(true)
      const token = tokenRef.current
      createSynthesis(input)
        .then((created) => {
          if (tokenRef.current !== token) {
            if (!created.reused) {
              cancelSynthesis(created.id).catch(() => undefined)
            }
            return
          }
          ownedRef.current = created.reused ? null : created.id
          setSeed(created)
          setJobId(created.id)
          setCreating(false)
        })
        .catch((cause: unknown) => {
          if (tokenRef.current === token) {
            setCreating(false)
            setError(cause instanceof SynthesisApiError ? cause.message : translate('err.synth.generic', { code: 'unknown' }))
          }
        })
    },
    [release],
  )

  const state = job?.state
  const audioUrl = job?.audio ? synthesisAudioUrl(job.id) : null
  useEffect(() => {
    if (jobId === null || state !== 'COMPLETED' || audioUrl === null || audioRef.current !== null) {
      return
    }
    const audio = new Audio(audioUrl)
    audioRef.current = audio
    audio.addEventListener('ended', finish)
    audio.addEventListener('error', () => {
      setError(messageForSynthesisError('synthesis_audio_missing'))
      finish()
    })
    setPlaying(true)
    Promise.resolve(audio.play()).catch(() => {
      setError(translate('speak.sample.blocked'))
      finish()
    })
  }, [jobId, state, audioUrl, finish])

  // Un fallo del trabajo se muestra y la muestra vuelve a reposo.
  const failure = state === 'FAILED' ? messageForSynthesisError(job?.error_code ?? 'synthesis_failed') : null

  useEffect(() => release, [release])

  const terminal = state === 'FAILED' || state === 'CANCELLED'
  const phase: SamplePhase = creating
    ? 'preparing'
    : jobId === null || terminal
      ? 'idle'
      : playing
        ? 'playing'
        : 'preparing'
  const stop = useCallback(() => {
    release()
    setError(null)
  }, [release])
  return { phase, error: error ?? failure, start, stop }
}
