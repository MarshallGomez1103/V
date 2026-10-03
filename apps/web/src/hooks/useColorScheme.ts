import { useEffect, useState } from 'react'

export type CarbonScheme = 'g100' | 'g10'

const QUERY = '(prefers-color-scheme: light)'

function current(): CarbonScheme {
  return typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia(QUERY).matches
    ? 'g10'
    : 'g100'
}

/**
 * Tema Carbon según el sistema: `g100` (oscuro) por defecto y `g10` si el
 * sistema prefiere claro. También pone la clase de zona en <html> para que los
 * portales (menús, tooltips) y el fondo del documento hereden el mismo tema.
 */
export function useColorScheme(): CarbonScheme {
  const [scheme, setScheme] = useState<CarbonScheme>(current)

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') {
      return
    }
    const media = window.matchMedia(QUERY)
    const update = () => {
      setScheme(media.matches ? 'g10' : 'g100')
    }
    media.addEventListener('change', update)
    return () => {
      media.removeEventListener('change', update)
    }
  }, [])

  useEffect(() => {
    const root = document.documentElement
    root.classList.remove('cds--g100', 'cds--g10')
    root.classList.add('cds--' + scheme)
    return () => {
      root.classList.remove('cds--' + scheme)
    }
  }, [scheme])

  return scheme
}
