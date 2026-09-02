import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Home de VOZ', () => {
  it('presenta la importación como futura y muestra la API disponible', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({ status: 'ok', service: 'voz', version: '0.1.0' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(
      screen.getByRole('heading', { name: /escucha menos/i }),
    ).toBeDefined()
    expect(
      screen.getByRole('button', { name: /importar archivo/i }),
    ).toHaveProperty('disabled', true)
    expect(
      screen.getByText(/todavía no se cargará ni procesará ningún archivo/i),
    ).toBeDefined()

    expect(await screen.findByText('Disponible')).toBeDefined()
    expect(screen.getByText(/v0\.1\.0/i)).toBeDefined()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/health',
      expect.objectContaining({
        headers: { Accept: 'application/json' },
      }),
    )
  })

  it('permite volver a comprobar la API después de una desconexión', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ status: 'ok', service: 'voz' }),
      })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('Sin conexión')).toBeDefined()
    expect(
      screen.getByText(/inicia el servidor local para conectar la interfaz/i),
    ).toBeDefined()

    fireEvent.click(
      screen.getByRole('button', { name: /volver a comprobar/i }),
    )

    expect(await screen.findByText('Disponible')).toBeDefined()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
