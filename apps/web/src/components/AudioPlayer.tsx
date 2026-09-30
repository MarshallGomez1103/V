import { useEffect, useRef } from 'react'

export interface AudioPlayerProps {
  mediaAssetId: string | null
  seekToMs: number | null
  seekNonce: number
  // S5.11: posición actual en ms enteros (eventos nativos timeupdate/seeked).
  onTimeUpdate?: (ms: number) => void
}

function originalMediaUrl(mediaAssetId: string): string {
  return '/api/media/' + encodeURIComponent(mediaAssetId) + '/original'
}

// S5.08: reproductor nativo del original; el navegador pide rangos al backend.
// S5.10: el padre conecta `useSeek()` (hooks/useSeek.ts) a seekToMs/seekNonce.
export function AudioPlayer({
  mediaAssetId,
  seekToMs,
  seekNonce,
  onTimeUpdate,
}: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null)

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

  const reportTime = (audio: HTMLAudioElement) => {
    onTimeUpdate?.(Math.round(audio.currentTime * 1000))
  }

  return (
    <div className="audio-player">
      <audio
        ref={audioRef}
        controls
        preload="metadata"
        src={originalMediaUrl(mediaAssetId)}
        aria-label="Reproductor del original"
        onTimeUpdate={(event) => {
          reportTime(event.currentTarget)
        }}
        onSeeked={(event) => {
          reportTime(event.currentTarget)
        }}
      />
    </div>
  )
}
