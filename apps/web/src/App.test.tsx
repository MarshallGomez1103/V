import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

describe('App', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the import card enabled and the health status', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ status: 'ok', service: 'voz' }),
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
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
