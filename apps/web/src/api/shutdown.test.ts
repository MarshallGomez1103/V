import { afterEach, describe, expect, it, vi } from 'vitest'

import { shutdownServer, ShutdownError } from './shutdown'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

const resp = (status: number, body: unknown = {}) =>
  Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body) })

describe('shutdownServer', () => {
  it('envía POST con la cabecera X-VOZ-Action: shutdown y resuelve con 202', async () => {
    const fetchMock = vi.fn().mockImplementation(() => resp(202, { status: 'stopping' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(shutdownServer()).resolves.toBeUndefined()
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/shutdown')
    expect(init.method).toBe('POST')
    expect(init.headers).toMatchObject({ 'X-VOZ-Action': 'shutdown' })
  })

  it('lanza el código del error del backend', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => resp(501, { detail: { code: 'shutdown_unavailable' } })),
    )
    await expect(shutdownServer()).rejects.toMatchObject({
      name: 'ShutdownError',
      code: 'shutdown_unavailable',
    })
  })

  it('si la respuesta se perdió pero el servidor ya no contesta, cuenta como cerrado', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.reject(new TypeError('red'))))
    const pending = shutdownServer()
    await vi.advanceTimersByTimeAsync(1000)
    await expect(pending).resolves.toBeUndefined()
  })

  it('si falla la red pero el servidor sigue vivo, es un error', async () => {
    vi.useFakeTimers()
    let calls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        calls += 1
        return url.includes('/api/health') ? resp(200) : Promise.reject(new TypeError('red'))
      }),
    )
    const pending = shutdownServer()
    const assertion = expect(pending).rejects.toBeInstanceOf(ShutdownError)
    await vi.advanceTimersByTimeAsync(1000)
    await assertion
    expect(calls).toBe(2)
  })
})
