import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { setLang } from '../i18n/i18n'
import { AppVersion } from './AppVersion'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  setLang('es')
})

function stubHealth(response: () => Promise<unknown>) {
  const fetchMock = vi.fn().mockImplementation(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const ok = (body: unknown) => () =>
  Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) })

describe('AppVersion', () => {
  it('muestra la versión leída de /api/health en español', async () => {
    setLang('es')
    stubHealth(ok({ status: 'ok', version: '0.1.0' }))
    render(<AppVersion active />)

    expect(await screen.findByText('Versión v0.1.0')).toBeTruthy()
  })

  it('muestra la versión en inglés', async () => {
    setLang('en')
    stubHealth(ok({ status: 'ok', version: '0.1.0' }))
    render(<AppVersion active />)

    expect(await screen.findByText('Version v0.1.0')).toBeTruthy()
  })

  it('no muestra nada mientras carga ni consulta con el menú cerrado', () => {
    const fetchMock = stubHealth(() => new Promise(() => undefined))
    const { container, rerender } = render(<AppVersion active={false} />)
    expect(fetchMock).not.toHaveBeenCalled()

    rerender(<AppVersion active />)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(container.textContent).toBe('')
  })

  it('no muestra nada ni lanza si health falla', async () => {
    const fetchMock = stubHealth(() => Promise.reject(new TypeError('network')))
    const { container } = render(<AppVersion active />)

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled()
    })
    expect(container.textContent).toBe('')
  })

  it('no muestra nada si health responde sin versión o con error HTTP', async () => {
    stubHealth(ok({ status: 'ok' }))
    const first = render(<AppVersion active />)
    await waitFor(() => {
      expect(vi.mocked(fetch)).toHaveBeenCalled()
    })
    expect(first.container.textContent).toBe('')
    first.unmount()

    stubHealth(() => Promise.resolve({ ok: false, status: 503, json: () => Promise.resolve({}) }))
    const second = render(<AppVersion active />)
    await waitFor(() => {
      expect(vi.mocked(fetch)).toHaveBeenCalled()
    })
    expect(second.container.textContent).toBe('')
  })
})
