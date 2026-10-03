import { useEffect, useState } from 'react'

/** Reloj que avanza cada `intervalMs` (1 s) mientras `running`; sirve para contadores en vivo. */
export function useNow(running: boolean, intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!running) {
      return
    }
    const tick = () => {
      setNow(Date.now())
    }
    // Primer valor al instante (no esperar un segundo) y luego cada intervalo.
    const first = setTimeout(tick, 0)
    const timer = setInterval(tick, intervalMs)
    return () => {
      clearTimeout(first)
      clearInterval(timer)
    }
  }, [running, intervalMs])

  return now
}
