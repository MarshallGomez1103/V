/**
 * S7.06: posición del reproductor como store externo. Permite que solo la
 * palabra activa se re-renderice sin pasar `currentMs` por props (lo que
 * invalidaría las filas memoizadas de SegmentList en cada tick).
 */
export interface Playhead {
  get: () => number | undefined
  set: (ms: number | undefined) => void
  subscribe: (listener: () => void) => () => void
}

export function createPlayhead(): Playhead {
  let current: number | undefined
  const listeners = new Set<() => void>()
  return {
    get: () => current,
    set: (ms) => {
      if (ms === current) {
        return
      }
      current = ms
      listeners.forEach((listener) => {
        listener()
      })
    },
    subscribe: (listener) => {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
  }
}
