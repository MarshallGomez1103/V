import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ProviderView } from '../api/providers'
import { useCloudProviders } from './useCloudProviders'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const CLASSIC: ProviderView = {
  id: 'openai', label: 'OpenAI', privacy_url: 'https://example.test/privacy',
  configured: true, cloud: true,
}

function option(providerId = 'openai-compatible-cloud', overrides: Record<string, unknown> = {}) {
  return {
    option_id: 'option-' + providerId, provider_id: providerId, model_id: 'test-model',
    source: null, revision: null, profile: null, display_name: 'Test model',
    installation_status: 'registered', files_available: true, runtime_available: true,
    can_start: true, capabilities: ['transcription'], execution: null, device_name: null,
    recommendation: null, blocking_reasons: [], cloud: true, provider_label: 'Servidor remoto',
    ...overrides,
  }
}

function stub(providers: unknown = [CLASSIC], options: unknown = [], failed: string[] = []) {
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>().mockImplementation((url) => {
    return Promise.resolve(new Response(JSON.stringify(url === '/api/providers' ? providers : { options }), {
      status: failed.includes(url) ? 503 : 200,
    }))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('useCloudProviders', () => {
  it('combina proveedores clásicos y cloud del catálogo sin duplicados ni proveedores locales', async () => {
    stub([CLASSIC], [
      option(), option(), option('otro-cloud', { provider_label: 'Otro servidor', can_start: false }),
      option('openai', { provider_label: 'Nombre alternativo' }),
      option('openai-compatible-local', { cloud: false, provider_label: null }),
      option('sin-metadatos', { cloud: undefined }),
    ])
    const { result } = renderHook(() => useCloudProviders(true))

    await waitFor(() => expect(result.current).toHaveLength(3))
    expect(result.current).toEqual(expect.arrayContaining([
      CLASSIC,
      { id: 'openai-compatible-cloud', label: 'Servidor remoto', cloud: true, privacy_url: null, configured: true },
      { id: 'otro-cloud', label: 'Otro servidor', cloud: true, privacy_url: null, configured: false },
    ]))
  })

  it('conserva los clásicos si falla transcription-options', async () => {
    stub([CLASSIC], [], ['/api/transcription-options'])
    const { result } = renderHook(() => useCloudProviders(true))
    await waitFor(() => expect(result.current).toEqual([CLASSIC]))
  })

  it('usa la etiqueta del modelo seleccionado si dos servidores comparten provider_id', async () => {
    stub([], [
      option('openai-compatible-cloud', { model_id: 'seleccionado', provider_label: 'Servidor elegido' }),
      option('openai-compatible-cloud', { model_id: 'otro', provider_label: 'Otro servidor' }),
    ])
    const { result } = renderHook(() => useCloudProviders(true, 'seleccionado'))
    await waitFor(() => expect(result.current).toEqual([
      { id: 'openai-compatible-cloud', label: 'Servidor elegido', cloud: true, privacy_url: null, configured: true },
    ]))
  })

  it('publica los clásicos aunque transcription-options quede pendiente', async () => {
    const fetchMock = stub()
    const respond = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((input, init) => input === '/api/transcription-options'
      ? new Promise<Response>(() => undefined)
      : respond(input, init))
    const { result } = renderHook(() => useCloudProviders(true))
    await waitFor(() => expect(result.current).toEqual([CLASSIC]))
  })

  it('usa cloud y provider_label del catálogo aunque falle providers', async () => {
    stub([], [option('proveedor-futuro')], ['/api/providers'])
    const { result } = renderHook(() => useCloudProviders(true))
    await waitFor(() => expect(result.current).toEqual([
      { id: 'proveedor-futuro', label: 'Servidor remoto', cloud: true, privacy_url: null, configured: true },
    ]))
  })

  it('no consulta desactivado y aborta ambas consultas al desmontarse', async () => {
    const fetchMock = stub()
    const { result, rerender, unmount } = renderHook(({ enabled }) => useCloudProviders(enabled), {
      initialProps: { enabled: false },
    })
    expect(result.current).toEqual([])
    expect(fetchMock).not.toHaveBeenCalled()
    await act(async () => {
      rerender({ enabled: true })
      await Promise.resolve()
    })
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(['/api/providers', '/api/transcription-options'])
    const signals = fetchMock.mock.calls.map(([, init]) => init?.signal)
    unmount()
    expect(signals.every((signal) => signal?.aborted)).toBe(true)
  })
})
