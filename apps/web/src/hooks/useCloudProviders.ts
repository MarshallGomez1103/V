import { useEffect, useState } from 'react'

import { isAbortError } from '../api/errors'
import { listProviders, type ProviderView } from '../api/providers'

/**
 * Proveedores cloud que publica el backend (fuente de verdad de id y nombre).
 * Solo consulta si `enabled`; ante un fallo devuelve la lista vacía: el aviso
 * cloud es informativo y no debe romper la pantalla.
 */
export function useCloudProviders(enabled: boolean): ProviderView[] {
  const [providers, setProviders] = useState<ProviderView[]>([])

  useEffect(() => {
    if (!enabled) {
      return
    }
    const controller = new AbortController()
    void listProviders(controller.signal)
      .then(setProviders)
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          setProviders([])
        }
      })
    return () => {
      controller.abort()
    }
  }, [enabled])

  return providers
}
