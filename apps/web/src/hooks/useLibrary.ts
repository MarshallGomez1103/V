import { useCallback, useEffect, useState } from 'react'

import { isAbortError } from '../api/errors'
import { fetchLibrary, type LibraryItem } from '../api/library'

export type LibraryState =
  | { phase: 'loading' }
  | { phase: 'error'; message: string | null }
  | { phase: 'ready'; items: LibraryItem[] }

/** Biblioteca de transcripciones de este equipo, del proyecto más reciente al más antiguo. */
export function useLibrary(): LibraryState & { reload: () => void } {
  const [state, setState] = useState<LibraryState>({ phase: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    void fetchLibrary(controller.signal)
      .then((items) => {
        setState({
          phase: 'ready',
          items: [...items].sort((a, b) => b.created_at.localeCompare(a.created_at)),
        })
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          setState({ phase: 'error', message: error instanceof Error ? error.message : null })
        }
      })
    return () => {
      controller.abort()
    }
  }, [attempt])

  const reload = useCallback(() => {
    setState((current) => (current.phase === 'error' ? { phase: 'loading' } : current))
    setAttempt((current) => current + 1)
  }, [])

  return { ...state, reload }
}
