import { afterEach, describe, expect, it, vi } from 'vitest'

import { createShortcut, getShortcutStatus, removeShortcut, ShortcutError } from './desktopShortcut'

afterEach(() => {
  vi.unstubAllGlobals()
})

const resp = (status: number, body: unknown) =>
  Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body) })

describe('desktopShortcut', () => {
  it('lee el estado y descarta la ruta del equipo', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => resp(200, { supported: true, exists: false, path: '/home/x/VOZ.desktop' })),
    )
    const status = await getShortcutStatus()
    expect(status).toEqual({ supported: true, exists: false, broken: false })
    expect(JSON.stringify(status)).not.toContain('/home')
  })

  it('si el servidor no ofrece la función o responde algo raro, devuelve null', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => resp(404, { detail: 'Not Found' })))
    expect(await getShortcutStatus()).toBeNull()
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => resp(200, { nada: 1 })))
    expect(await getShortcutStatus()).toBeNull()
  })

  it('crear envía POST con la cabecera X-VOZ-Action: desktop-shortcut', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementation(() => resp(200, { supported: true, exists: true, path: '/x' }))
    vi.stubGlobal('fetch', fetchMock)

    expect(await createShortcut()).toEqual({ supported: true, exists: true, broken: false })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/desktop-shortcut')
    expect(init.method).toBe('POST')
    expect(init.headers).toMatchObject({ 'X-VOZ-Action': 'desktop-shortcut' })
  })

  it('un error del backend sale con su código', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => resp(500, { detail: { code: 'shortcut_failed' } })),
    )
    await expect(createShortcut()).rejects.toBeInstanceOf(ShortcutError)
    await expect(createShortcut()).rejects.toMatchObject({ code: 'shortcut_failed' })
  })

  it('lee el estado roto (el archivo está pero apunta a una carpeta que ya no existe)', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockImplementation(() => resp(200, { supported: true, exists: false, broken: true, path: '~/v' })),
    )
    expect(await getShortcutStatus()).toEqual({ supported: true, exists: false, broken: true })
  })

  it('quitar envía DELETE con su propia cabecera X-VOZ-Action', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementation(() => resp(200, { supported: true, exists: false, broken: false, path: null }))
    vi.stubGlobal('fetch', fetchMock)

    expect(await removeShortcut()).toEqual({ supported: true, exists: false, broken: false })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/desktop-shortcut')
    expect(init.method).toBe('DELETE')
    expect(init.headers).toMatchObject({ 'X-VOZ-Action': 'remove-desktop-shortcut' })
  })

  it('quitar con error del backend sale con su código', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockImplementation(() => resp(500, { detail: { code: 'desktop_shortcut_remove_failed' } })),
    )
    await expect(removeShortcut()).rejects.toMatchObject({ code: 'desktop_shortcut_remove_failed' })
  })
})
