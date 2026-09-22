import { useCallback, useState } from 'react'

export interface SeekState {
  seekToMs: number | null
  seekNonce: number
  seek: (ms: number) => void
}

// S5.10: cada llamada incrementa el nonce para que un seek repetido al mismo
// instante también dispare el efecto del reproductor.
export function useSeek(): SeekState {
  const [seekToMs, setSeekToMs] = useState<number | null>(null)
  const [seekNonce, setSeekNonce] = useState(0)

  const seek = useCallback((ms: number) => {
    setSeekToMs(ms)
    setSeekNonce((nonce) => nonce + 1)
  }, [])

  return { seekToMs, seekNonce, seek }
}
