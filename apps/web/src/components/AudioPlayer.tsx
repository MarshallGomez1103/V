import { useEffect, useRef, useState } from 'react'
import { Button, IconButton } from '@carbon/react'
import {
  Forward_5,
  Pause,
  PlayFilledAlt,
  Rewind_5,
  VolumeMute,
  VolumeUp,
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
}

const RATES = [1, 1.25, 1.5, 2, 0.75] as const
const SKIP_SECONDS = 5

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
}: AudioPlayerProps) {
  const { t } = useI18n()
  const audioRef = useRef<HTMLAudioElement>(null)
  const [time, setTime] = useState(0)
  const [measured, setMeasured] = useState<number | null>(null)
  const [playing, setPlaying] = useState(false)
  const [volume, setVolume] = useState(1)
  const [muted, setMuted] = useState(false)
  const [rate, setRate] = useState<(typeof RATES)[number]>(1)

  useEffect(() => {
    const audio = audioRef.current
    if (seekNonce === 0 || seekToMs === null || audio === null) {
      return
    }
    audio.currentTime = Math.max(0, seekToMs) / 1000
    const playback: unknown = audio.play()
    if (playback instanceof Promise) {
      // El autoplay puede estar bloqueado; el usuario aún puede pulsar play.
      playback.catch(() => undefined)
    }
  }, [seekNonce, seekToMs])

  if (mediaAssetId === null) {
    return null
  }

  const duration =
    measured !== null && Number.isFinite(measured) && measured > 0
      ? measured
      : durationMs !== null
        ? durationMs / 1000
        : 0

  const sync = (audio: HTMLAudioElement) => {
    setTime(audio.currentTime)
    onTimeUpdate?.(Math.round(audio.currentTime * 1000))
  }

  const toggle = () => {
    const audio = audioRef.current
    if (audio === null) {
      return
    }
    if (audio.paused) {
      const playback: unknown = audio.play()
      if (playback instanceof Promise) {
        playback.catch(() => undefined)
      }
    } else {
      audio.pause()
    }
  }

  const jump = (seconds: number) => {
    const audio = audioRef.current
    if (audio === null) {
      return
    }
    const limit = duration > 0 ? duration : Number.MAX_SAFE_INTEGER
    audio.currentTime = Math.min(limit, Math.max(0, audio.currentTime + seconds))
    sync(audio)
  }

  const cycleRate = () => {
    const next = RATES[(RATES.indexOf(rate) + 1) % RATES.length] ?? 1
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
        src={originalMediaUrl(mediaAssetId)}
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
          label={t('audio.back', { seconds: SKIP_SECONDS })}
          onClick={() => {
            jump(-SKIP_SECONDS)
          }}
        >
          <Rewind_5 />
        </IconButton>
        <IconButton
          kind="primary"
          size="md"
          label={playing ? t('audio.pause') : t('audio.play')}
          onClick={toggle}
        >
          {playing ? <Pause /> : <PlayFilledAlt />}
        </IconButton>
        <IconButton
          kind="ghost"
          size="md"
          label={t('audio.forward', { seconds: SKIP_SECONDS })}
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
              audio.currentTime = Number(event.currentTarget.value)
              sync(audio)
            }
          }}
        />
        <div className="voz-player__volume">
          <IconButton
            kind="ghost"
            size="md"
            label={muted ? t('audio.unmute') : t('audio.mute')}
            onClick={() => {
              const next = !muted
              setMuted(next)
              if (audioRef.current) {
                audioRef.current.muted = next
              }
            }}
          >
            {muted || volume === 0 ? <VolumeMute /> : <VolumeUp />}
          </IconButton>
          <input
            type="range"
            className="voz-range voz-player__volumebar"
            min={0}
            max={1}
            step={0.05}
            value={muted ? 0 : volume}
            style={fillStyle(muted ? 0 : volume, 1)}
            aria-label={t('audio.volume')}
            onChange={(event) => {
              const next = Number(event.currentTarget.value)
              setVolume(next)
              setMuted(false)
              if (audioRef.current) {
                audioRef.current.volume = next
                audioRef.current.muted = false
              }
            }}
          />
        </div>
        <Button
          kind="ghost"
          size="md"
          className="voz-player__rate"
          title={t('audio.rate.hint')}
          aria-label={t('audio.rate', { rate: String(rate) })}
          onClick={cycleRate}
        >
          {String(rate) + '×'}
        </Button>
      </div>
    </div>
  )
}
