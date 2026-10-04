import { useCallback, useState } from 'react'

export interface SeekState {
  seekToMs: number | null
  seekNonce: number
  /** Si no es `null`, el reproductor se pausa al llegar a ese instante (muestras). */
  stopAtMs: number | null
  seek: (ms: number, stopAtMs?: number) => void
}

// S5.10: cada llamada incrementa el nonce para que un seek repetido al mismo
// instante también dispare el efecto del reproductor.
export function useSeek(): SeekState {
  const [target, setTarget] = useState<{ ms: number | null; stop: number | null }>({
    ms: null,
    stop: null,
  })
  const [seekNonce, setSeekNonce] = useState(0)

  const seek = useCallback((ms: number, stopAtMs?: number) => {
    setTarget({ ms, stop: stopAtMs ?? null })
    setSeekNonce((nonce) => nonce + 1)
  }, [])

  return { seekToMs: target.ms, seekNonce, stopAtMs: target.stop, seek }
}
