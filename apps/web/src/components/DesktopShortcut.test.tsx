import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DesktopShortcut } from './DesktopShortcut'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

interface Status {
  supported: boolean
  exists: boolean
  broken: boolean
}

function stubApi(initial: Status, options: { removeStatus?: number } = {}) {
  const calls: { method: string; headers: Record<string, string> }[] = []
  let state = initial
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      calls.push({ method, headers: (init?.headers ?? {}) as Record<string, string> })
      let status = 200
      if (method === 'POST') {
        state = { ...state, exists: true, broken: false }
        status = 201
      }
      if (method === 'DELETE') {
        status = options.removeStatus ?? 200
        if (status < 300) {
          state = { ...state, exists: false, broken: false }
        }
      }
      const body = status < 300 ? { ...state, path: null } : { detail: { code: 'x', message: 'x' } }
      return Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body) })
    }),
  )
  return calls
}

describe('DesktopShortcut', () => {
  it('muestra el estado roto y deja volver a crearlo o quitarlo', async () => {
    stubApi({ supported: true, exists: false, broken: true })
    render(<DesktopShortcut active />)

    expect(
      await screen.findByText(
        'El acceso directo apunta a una carpeta que ya no existe: vuelve a crearlo.',
      ),
    ).toBeDefined()
    expect(screen.getByRole('button', { name: 'Volver a crearlo' })).toBeDefined()
    expect(screen.getByRole('button', { name: 'Quitar acceso directo' })).toBeDefined()
  })

  it('volver a crearlo limpia el aviso de roto', async () => {
    stubApi({ supported: true, exists: false, broken: true })
    render(<DesktopShortcut active />)

    fireEvent.click(await screen.findByRole('button', { name: 'Volver a crearlo' }))

    expect(await screen.findByText('Icono creado en el escritorio.')).toBeDefined()
    expect(screen.queryByText(/ya no existe/)).toBeNull()
  })

  it('quitar pide confirmación y solo entonces envía DELETE', async () => {
    const calls = stubApi({ supported: true, exists: true, broken: false })
    render(<DesktopShortcut active />)

    fireEvent.click(await screen.findByRole('button', { name: 'Quitar acceso directo' }))
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false)
    expect(screen.getByText(/V sigue instalado/)).toBeDefined()

    fireEvent.click(screen.getByRole('button', { name: 'Quitar' }))

    expect(await screen.findByText('Acceso directo quitado.')).toBeDefined()
    const sent = calls.find((call) => call.method === 'DELETE')
    expect(sent?.headers['X-VOZ-Action']).toBe('remove-desktop-shortcut')
    expect(screen.getByRole('button', { name: 'Crear icono en el escritorio' })).toBeDefined()
    expect(screen.queryByRole('button', { name: 'Quitar acceso directo' })).toBeNull()
  })

  it('cancelar la confirmación no borra nada', async () => {
    const calls = stubApi({ supported: true, exists: true, broken: false })
    render(<DesktopShortcut active />)

    fireEvent.click(await screen.findByRole('button', { name: 'Quitar acceso directo' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))

    expect(screen.getByRole('button', { name: 'Quitar acceso directo' })).toBeDefined()
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false)
  })

  it('si quitar falla lo dice y el botón sigue disponible', async () => {
    stubApi({ supported: true, exists: true, broken: false }, { removeStatus: 500 })
    render(<DesktopShortcut active />)

    fireEvent.click(await screen.findByRole('button', { name: 'Quitar acceso directo' }))
    fireEvent.click(screen.getByRole('button', { name: 'Quitar' }))

    expect(await screen.findByText(/No se pudo quitar el acceso directo/)).toBeDefined()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Quitar acceso directo' })).toBeDefined()
    })
  })

  it('sin soporte pero con un acceso directo roto, deja quitarlo (sin ofrecer crearlo)', async () => {
    stubApi({ supported: false, exists: false, broken: true })
    render(<DesktopShortcut active />)

    expect(await screen.findByRole('button', { name: 'Quitar acceso directo' })).toBeDefined()
    expect(screen.queryByRole('button', { name: 'Volver a crearlo' })).toBeNull()
  })

  it('sin soporte y sin nada que quitar, no muestra nada', async () => {
    const calls = stubApi({ supported: false, exists: false, broken: false })
    const { container } = render(<DesktopShortcut active />)

    await waitFor(() => {
      expect(calls.length).toBeGreaterThan(0)
    })
    expect(container.textContent).toBe('')
  })
})
