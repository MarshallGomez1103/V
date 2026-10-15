import { useEffect, useState } from 'react'

import { listProviders, type ProviderView } from '../api/providers'
import { getTranscriptionOptions, type TranscriptionOption } from '../api/transcriptionOptions'

type CloudAwareOption = TranscriptionOption & {
  cloud?: unknown
  provider_label?: unknown
}

/**
 * Proveedores clásicos y opciones cloud publicados por el backend.
 * Solo consulta si `enabled`; un fallo conserva los datos de la otra fuente.
 */
export function useCloudProviders(enabled: boolean, modelId?: string | null): ProviderView[] {
  const [sources, setSources] = useState<{ classic: ProviderView[]; catalog: ProviderView[] }>({
    classic: [], catalog: [],
  })

  useEffect(() => {
    if (!enabled) {
      return
    }
    const controller = new AbortController()
    const update = (source: 'classic' | 'catalog', providers: ProviderView[]) => {
      if (!controller.signal.aborted) {
        setSources((current) => ({ ...current, [source]: providers }))
      }
    }
    void listProviders(controller.signal)
      .then((providers) => update('classic', providers))
      .catch(() => update('classic', []))
    void getTranscriptionOptions(controller.signal)
      .then((payload) => {
        const options: CloudAwareOption[] = payload.options
        update('catalog', options.filter((option) => option.cloud === true && (modelId == null || option.model_id === modelId)).map((option) => ({
          id: option.provider_id,
          label: typeof option.provider_label === 'string' ? option.provider_label : option.provider_id,
          privacy_url: null,
          configured: option.can_start,
          cloud: true,
        })))
      })
      .catch(() => update('catalog', []))
    return () => {
      controller.abort()
    }
  }, [enabled, modelId])

  return [...new Map([...sources.catalog, ...sources.classic].map((provider) => [provider.id, provider])).values()]
}
