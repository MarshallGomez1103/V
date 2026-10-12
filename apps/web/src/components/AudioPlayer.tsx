import { useEffect, useRef, useState } from 'react'
import { Dropdown, IconButton } from '@carbon/react'
import {
  Forward_5,
  Pause,
  PlayFilledAlt,
  Rewind_5,
  VolumeMute,
  VolumeUp,
  WarningAltFilled,
} from '@carbon/icons-react'

import { useI18n } from '../i18n/i18n'
import { formatSeconds } from '../lib/formatTime'
import './AudioPlayer.scss'

export interface AudioPlayerProps {
  mediaAssetId: string | null
  seekToMs: number | null
  seekNonce: number
  // S5.11: posición actual en ms enteros (eventos nativos timeupdate/seeked).
  onTimeUpdate?: (ms: number) => void
  /** Duración conocida por la importación; sirve mientras el navegador no la mide. */
  durationMs?: number | null
  /** Con un seek: pausa al llegar a este instante (muestras de un hablante). */
  stopAtMs?: number | null
  /** URL del audio si no es el original de un medio (p. ej. un WAV sintetizado); `mediaAssetId` sirve de id. */
  src?: string
}

const RATES = [0.5, 0.75, 1, 1.25, 1.5, 2] as const
type Rate = (typeof RATES)[number]
const SKIP_SECONDS = 5
const MAX_PERCENT = 300

interface Boost {
  ctx: AudioContext
  gain: GainNode
}

function audioContextClass(): typeof AudioContext | null {
  if (typeof window === 'undefined') {
    return null
  }
  const legacy = (window as unknown as { webkitAudioContext?: typeof AudioContext })
    .webkitAudioContext
  return typeof AudioContext === 'undefined' ? (legacy ?? null) : AudioContext
}

/** Teclas de atajo que no deben robarse cuando se está escribiendo o en un menú. */
function ownsKeys(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false
  }
  if (target instanceof HTMLInputElement && target.type === 'range') {
    return false
  }
  return (
    target.isContentEditable ||
    target.matches('input, textarea, select, [contenteditable], [role=combobox], [role=listbox], [role=option], [role=menuitem]') ||
    target.closest('.cds--modal, [role=dialog]') !== null
  )
}

function originalMediaUrl(mediaAssetId: string): string {
  return '/api/media/' + encodeURIComponent(mediaAssetId) + '/original'
}

/** Porcentaje para pintar la parte llena de una barra `range`. */
function fillStyle(value: number, max: number) {
  const percent = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0
  return { '--voz-fill': String(percent) + '%' } as React.CSSProperties
}

// S5.08: el navegador reproduce el original (pide rangos al backend); los controles
// son de la app (Carbon), no el reproductor nativo.
// S5.10: el padre conecta `useSeek()` (hooks/useSeek.ts) a seekToMs/seekNonce.
export function AudioPlayer({
  mediaAssetId,
  seekToMs,
  seekNonce,
  onTimeUpdate,
  durationMs = null,
  stopAtMs = null,
  src,
}: AudioPlayerProps) {
  const { t } = useI18n()
  const audioRef = useRef<HTMLAudioElement>(null)
  const [time, setTime] = useState(0)
  const [measured, setMeasured] = useState<number | null>(null)
  const [playing, setPlaying] = useState(false)
  // Volumen en % (0–300). Hasta 100 % lo da el propio audio; más arriba entra un
  // GainNode de Web Audio, que se crea una sola vez (un elemento admite una sola fuente).
  const [percent, setPercent] = useState(100)
  const [muted, setMuted] = useState(false)
  const [rate, setRate] = useState<Rate>(1)
  const boostRef = useRef<Boost | null>(null)
  const stopRef = useRef<number | null>(null)
  const canBoost = audioContextClass() !== null
  const maxPercent = canBoost ? MAX_PERCENT : 100

  useEffect(() => {
    const audio = audioRef.current
    if (seekNonce === 0 || seekToMs === null || audio === null) {
      return
    }
    audio.currentTime = Math.max(0, seekToMs) / 1000
    stopRef.current = stopAtMs
    void boostRef.current?.ctx.resume().catch(() => undefined)
    const playback: unknown = audio.play()
    if (playback instanceof Promise) {
      // El autoplay puede estar bloqueado; el usuario aún puede pulsar play.
      playback.catch(() => undefined)
    }
  }, [seekNonce, seekToMs, stopAtMs])

  // Al desmontar se libera el contexto de audio, si llegó a crearse.
  useEffect(
    () => () => {
      const boost = boostRef.current
      boostRef.current = null
      void boost?.ctx.close().catch(() => undefined)
    },
    [],
  )

  const durationSeconds =
    measured !== null && Number.isFinite(measured) && measured > 0
      ? measured
      : durationMs !== null
        ? durationMs / 1000
        : 0
  // Atajos globales: Espacio reproduce o pausa; ← y → mueven 5 s.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const audio = audioRef.current
      if (
        audio === null ||
        event.defaultPrevented ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.shiftKey ||
        ownsKeys(event.target)
      ) {
        return
      }
      const onButton = event.target instanceof HTMLElement && event.target.closest('button, a, summary') !== null
      if (event.code === 'Space' && !onButton) {
        event.preventDefault()
        playOrPause(audio, boostRef.current)
      } else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        if (event.target instanceof HTMLInputElement) {
          return
        }
        event.preventDefault()
        stopRef.current = null
        const limit = durationSeconds > 0 ? durationSeconds : Number.MAX_SAFE_INTEGER
        const delta = event.key === 'ArrowLeft' ? -SKIP_SECONDS : SKIP_SECONDS
        audio.currentTime = Math.min(limit, Math.max(0, audio.currentTime + delta))
        setTime(audio.currentTime)
        onTimeUpdate?.(Math.round(audio.currentTime * 1000))
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
    }
  }, [durationSeconds, onTimeUpdate])

  if (mediaAssetId === null) {
    return null
  }

  const duration = durationSeconds

  const sync = (audio: HTMLAudioElement) => {
    setTime(audio.currentTime)
    onTimeUpdate?.(Math.round(audio.currentTime * 1000))
    if (stopRef.current !== null && audio.currentTime * 1000 >= stopRef.current) {
      stopRef.current = null
      audio.pause()
    }
  }

  const toggle = () => {
    const audio = audioRef.current
    if (audio !== null) {
      playOrPause(audio, boostRef.current)
    }
  }

  /** Aplica volumen (0–300 %) y silencio al audio o, si ya existe, al GainNode. */
  const applyVolume = (nextPercent: number, nextMuted: boolean) => {
    const audio = audioRef.current
    if (audio === null) {
      return
    }
    const level = nextMuted ? 0 : nextPercent / 100
    if (boostRef.current === null && level > 1) {
      const Context = audioContextClass()
      if (Context !== null) {
        try {
          const ctx = new Context()
          const gain = ctx.createGain()
          ctx.createMediaElementSource(audio).connect(gain)
          gain.connect(ctx.destination)
          boostRef.current = { ctx, gain }
        } catch {
          // Sin Web Audio el tope queda en 100 %.
        }
      }
    }
    const boost = boostRef.current
    if (boost !== null) {
      boost.gain.gain.value = level
      audio.volume = 1
      audio.muted = false
      void boost.ctx.resume().catch(() => undefined)
    } else {
      audio.volume = Math.min(1, level)
      audio.muted = nextMuted
    }
  }

  const jump = (seconds: number) => {
    const audio = audioRef.current
    if (audio === null) {
      return
    }
    stopRef.current = null
    const limit = duration > 0 ? duration : Number.MAX_SAFE_INTEGER
    audio.currentTime = Math.min(limit, Math.max(0, audio.currentTime + seconds))
    sync(audio)
  }

  const changeRate = (next: Rate) => {
    setRate(next)
    if (audioRef.current) {
      audioRef.current.playbackRate = next
    }
  }

  return (
    <div className="voz-player" role="group" aria-label={t('audio.group')}>
      <audio
        ref={audioRef}
        preload="metadata"
        src={src ?? originalMediaUrl(mediaAssetId)}
        aria-label={t('audio.element')}
        onTimeUpdate={(event) => {
          sync(event.currentTarget)
        }}
        onSeeked={(event) => {
          sync(event.currentTarget)
        }}
        onLoadedMetadata={(event) => {
          setMeasured(event.currentTarget.duration)
        }}
        onDurationChange={(event) => {
          setMeasured(event.currentTarget.duration)
        }}
        onPlay={() => {
          setPlaying(true)
          void boostRef.current?.ctx.resume().catch(() => undefined)
        }}
        onPause={() => {
          setPlaying(false)
        }}
        onEnded={() => {
          setPlaying(false)
        }}
      />
      <div className="voz-player__transport">
        <IconButton
          kind="ghost"
          size="md"
          label={t('audio.back', { seconds: SKIP_SECONDS }) + ' (←)'}
          onClick={() => {
            jump(-SKIP_SECONDS)
          }}
        >
          <Rewind_5 />
        </IconButton>
        <IconButton
          kind="primary"
          size="md"
          label={(playing ? t('audio.pause') : t('audio.play')) + ' (' + t('audio.key.space') + ')'}
          onClick={toggle}
        >
          {playing ? <Pause /> : <PlayFilledAlt />}
        </IconButton>
        <IconButton
          kind="ghost"
          size="md"
          label={t('audio.forward', { seconds: SKIP_SECONDS }) + ' (→)'}
          onClick={() => {
            jump(SKIP_SECONDS)
          }}
        >
          <Forward_5 />
        </IconButton>
        <output className="voz-player__clock" aria-label={t('audio.clock')}>
          <span>{formatSeconds(time)}</span>
          <span className="voz-player__sep"> / </span>
          <span>{formatSeconds(duration)}</span>
        </output>
        <input
          type="range"
          className="voz-range voz-player__position"
          min={0}
          max={Math.max(duration, 1)}
          step={0.1}
          value={Math.min(time, Math.max(duration, 1))}
          style={fillStyle(time, Math.max(duration, 1))}
          aria-label={t('audio.position')}
          aria-valuetext={formatSeconds(time) + ' / ' + formatSeconds(duration)}
          onChange={(event) => {
            const audio = audioRef.current
            if (audio) {
              stopRef.current = null
              audio.currentTime = Number(event.currentTarget.value)
              sync(audio)
            }
          }}
        />
        <div className="voz-player__volume" title={t('audio.vol.tip')}>
          <IconButton
            kind="ghost"
            size="md"
            label={muted ? t('audio.unmute') : t('audio.mute')}
            onClick={() => {
              const next = !muted
              setMuted(next)
              applyVolume(percent, next)
            }}
          >
            {muted || percent === 0 ? <VolumeMute /> : <VolumeUp />}
          </IconButton>
          <input
            type="range"
            className={
              'voz-range voz-player__volumebar' + (percent > 100 ? ' voz-player__volumebar--boost' : '')
            }
            min={0}
            max={maxPercent}
            step={5}
            value={muted ? 0 : percent}
            style={fillStyle(muted ? 0 : percent, maxPercent)}
            aria-label={t('audio.volume')}
            aria-valuetext={t('audio.vol.label', { percent: muted ? 0 : percent })}
            onChange={(event) => {
              const next = Number(event.currentTarget.value)
              setPercent(next)
              setMuted(false)
              applyVolume(next, false)
            }}
          />
          <output className="voz-player__percent" aria-hidden="true">
            {String(muted ? 0 : percent) + ' %'}
          </output>
        </div>
        <Dropdown
          id={'rate-' + mediaAssetId}
          className="voz-player__rate"
          size="md"
          label={t('audio.rate.label')}
          titleText={t('audio.rate.label')}
          hideLabel
          title={t('audio.rate.hint')}
          items={[...RATES]}
          selectedItem={rate}
          itemToString={(item) =>
            item === null || item === undefined
              ? ''
              : item === 1
                ? t('audio.rate.normal', { rate: item })
                : t('audio.rate.option', { rate: item })
          }
          onChange={({ selectedItem }) => {
            if (selectedItem !== null && selectedItem !== undefined) {
              changeRate(selectedItem)
            }
          }}
        />
      </div>
      {percent > 100 && !muted ? (
        <p className="voz-player__warn" role="status">
          <WarningAltFilled size={16} aria-hidden="true" />
          {t('audio.vol.warn')}
        </p>
      ) : null}
      <p className="voz-field-note voz-player__keys">{t('audio.keys')}</p>
    </div>
  )
}

function playOrPause(audio: HTMLAudioElement, boost: Boost | null): void {
  if (audio.paused) {
    void boost?.ctx.resume().catch(() => undefined)
    const playback: unknown = audio.play()
    if (playback instanceof Promise) {
      playback.catch(() => undefined)
    }
  } else {
    audio.pause()
  }
}
