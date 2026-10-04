import { useCallback, useEffect, useState } from 'react'

import { parseRoute, routeToHash, sameRoute, type Route } from '../lib/navigation'

/** Ruta actual, sincronizada con el hash de la URL (enlaces, Atrás/Adelante y recarga). */
export function useRoute(): [Route, (route: Route) => void] {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash))

  useEffect(() => {
    const onHashChange = () => {
      setRoute((current) => {
        const next = parseRoute(window.location.hash)
        return sameRoute(current, next) ? current : next
      })
    }
    window.addEventListener('hashchange', onHashChange)
    return () => {
      window.removeEventListener('hashchange', onHashChange)
    }
  }, [])

  const navigate = useCallback((next: Route) => {
    setRoute((current) => (sameRoute(current, next) ? current : next))
    const hash = routeToHash(next)
    if (window.location.hash !== hash) {
      window.location.hash = hash
    }
  }, [])

  return [route, navigate]
}
