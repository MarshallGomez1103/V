import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

describe('App', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the import card enabled and the health status', async () => {
    let healthCalls = 0
    const fetchMock = vi.fn((url: string) => {
      if (url.includes('/api/health')) {
        healthCalls += 1
        return healthCalls === 1
          ? Promise.reject(new Error('offline'))
          : Promise.resolve({
              ok: true,
              json: () => Promise.resolve({ status: 'ok', service: 'voz' }),
            })
      }
      // Otras secciones (p.ej. Modelos) cargan su propio estado.
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({ models: [], disk: { models_bytes: 0, free_bytes: null }, tasks: [] }),
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(
      screen.getByRole('button', { name: /importar archivo/i }),
    ).toHaveProperty('disabled', false)
    expect(screen.queryByText(/elige el motor/i)).toBeNull()
    expect(await screen.findByText('Sin conexión')).toBeDefined()

    fireEvent.click(
      screen.getByRole('button', { name: /volver a comprobar/i }),
    )

    expect(await screen.findByText('Disponible')).toBeDefined()
    expect(healthCalls).toBe(2)
  })
})
