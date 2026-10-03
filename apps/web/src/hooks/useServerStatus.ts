import { useCallback, useEffect, useRef, useState } from 'react'

export const UP_INTERVAL_MS = 5000
export const DOWN_INTERVAL_MS = 2000
/** Fallos seguidos antes de avisar: un tropiezo suelto no es una caída. */
export const FAILURES_BEFORE_DOWN = 2

export interface ServerStatus {
  /** `true` si el servidor local dejó de responder. */
  down: boolean
  /** Comprueba ya (botón «Reintentar»). */
  check: () => void
}

/**
 * Vigila `/api/health` mientras la pestaña está abierta: sin esto, si el servidor se
 * cae la pantalla se quedaría en blanco o cargando sin explicación.
 */
export function useServerStatus(enabled: boolean): ServerStatus {
  const [down, setDown] = useState(false)
  const [nonce, setNonce] = useState(0)
  const failures = useRef(0)

  useEffect(() => {
    if (!enabled) {
      return
    }
    let timer: ReturnType<typeof setTimeout> | undefined
    let cancelled = false

    const probe = async () => {
      try {
        const response = await fetch('/api/health', { cache: 'no-store' })
        if (!response.ok) {
          throw new Error('health')
        }
        failures.current = 0
        if (!cancelled) {
          setDown(false)
        }
      } catch {
        failures.current += 1
        if (!cancelled && failures.current >= FAILURES_BEFORE_DOWN) {
          setDown(true)
        }
      }
      if (!cancelled) {
        timer = setTimeout(
          () => void probe(),
          failures.current > 0 ? DOWN_INTERVAL_MS : UP_INTERVAL_MS,
        )
      }
    }
    // La primera comprobación espera un intervalo: la carga inicial ya consulta la API.
    timer = setTimeout(() => void probe(), nonce === 0 ? UP_INTERVAL_MS : 0)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [enabled, nonce])

  const check = useCallback(() => {
    failures.current = FAILURES_BEFORE_DOWN - 1
    setNonce((current) => current + 1)
  }, [])

  return { down, check }
}
