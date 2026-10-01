import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  deleteProviderKey,
  getEstimate,
  listProviders,
  messageForProviderError,
  ProviderApiError,
  saveProviderKey,
} from './providers'

afterEach(() => {
  vi.unstubAllGlobals()
})

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response
}

function emptyResponse(status: number): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.reject(new SyntaxError('sin cuerpo')),
  } as unknown as Response
}

function stubFetch(response: Response) {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const PROVIDER = {
  id: 'openai',
  label: 'OpenAI',
  privacy_url: null,
  configured: true,
  cloud: true,
}

describe('api/providers', () => {
  it('listProviders devuelve la lista validada', async () => {
    const fetchMock = stubFetch(
      jsonResponse(200, [PROVIDER]),
    )

    await expect(listProviders()).resolves.toEqual([PROVIDER])
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/providers',
      expect.objectContaining({ headers: { Accept: 'application/json' } }),
    )
  })

  it('listProviders rechaza formatos inesperados', async () => {
    stubFetch(jsonResponse(200, [{ id: 'openai' }]))

    await expect(listProviders()).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })

  it('saveProviderKey hace PUT con la clave en el cuerpo y acepta 204', async () => {
    const fetchMock = stubFetch(emptyResponse(204))

    await expect(saveProviderKey('openai', 'sk-abc')).resolves.toBeUndefined()

    const [url, init] = fetchMock.mock.calls[0] ?? []
    expect(url).toBe('/api/providers/openai/key')
    expect(init?.method).toBe('PUT')
    expect(init?.body).toBe(JSON.stringify({ key: 'sk-abc' }))
  })

  it('saveProviderKey traduce el código del backend a un mensaje en español', async () => {
    stubFetch(
      jsonResponse(409, {
        detail: { code: 'secrets_file_insecure', message: 'x' },
      }),
    )

    const error = await saveProviderKey('openai', 'sk-abc').catch(
      (caught: unknown) => caught,
    )

    expect(error).toBeInstanceOf(ProviderApiError)
    expect(error).toMatchObject({ code: 'secrets_file_insecure', status: 409 })
    expect((error as Error).message).toMatch(/0600/)
  })

  it('deleteProviderKey hace DELETE y es idempotente (204)', async () => {
    const fetchMock = stubFetch(emptyResponse(204))

    await deleteProviderKey('acme')

    const [url, init] = fetchMock.mock.calls[0] ?? []
    expect(url).toBe('/api/providers/acme/key')
    expect(init?.method).toBe('DELETE')
  })

  it('getEstimate envía media_asset_id y model y valida la respuesta', async () => {
    const estimate = {
      minutes: 5,
      usd: 0.03,
      price_source: 'https://platform.openai.com/pricing',
      price_date: '2026-09-30',
    }
    const fetchMock = stubFetch(jsonResponse(200, estimate))

    await expect(getEstimate('openai', 'm-1', 'whisper-1')).resolves.toEqual(
      estimate,
    )
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/api/providers/openai/estimate?media_asset_id=m-1&model=whisper-1',
    )
  })

  it('getEstimate propaga el código de error estable', async () => {
    stubFetch(
      jsonResponse(409, {
        detail: { code: 'media_duration_unknown', message: 'x' },
      }),
    )

    await expect(getEstimate('openai', 'm-1')).rejects.toMatchObject({
      code: 'media_duration_unknown',
      status: 409,
    })
  })

  it('un código desconocido deja el código visible y no revienta', () => {
    expect(messageForProviderError('raro')).toContain('raro')
    expect(messageForProviderError('constructor')).toContain('constructor')
  })

  it('listProviders rechaza una lista sin label', async () => {
    stubFetch(jsonResponse(200, [{ id: 'openai', configured: true, cloud: true }]))

    await expect(listProviders()).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })
})
