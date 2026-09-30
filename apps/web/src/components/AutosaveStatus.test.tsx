import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SegmentDraftStore } from '../hooks/useSegmentDrafts'
import { AutosaveStatus } from './AutosaveStatus'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const SEG = { id: 's1', text: 'original', revision: 1 }

describe('AutosaveStatus', () => {
  it('recorre Todo guardado, Cambios sin guardar, Guardando y de nuevo guardado', async () => {
    let resolve: (value: unknown) => void = () => undefined
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise((r) => {
            resolve = r
          }),
      ),
    )
    const store = new SegmentDraftStore()
    render(<AutosaveStatus drafts={store} />)

    expect(screen.getByRole('status').textContent).toBe('Todo guardado')

    act(() => {
      store.edit(SEG, 'nuevo')
    })
    expect(screen.getByRole('status').textContent).toBe('Cambios sin guardar')

    act(() => {
      store.flush('s1')
    })
    expect(screen.getByRole('status').textContent).toBe('Guardando…')

    await act(async () => {
      resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ id: 's1', text: 'nuevo', revision: 2 }),
      })
      await Promise.resolve()
    })
    expect(await screen.findByText('Todo guardado')).toBeTruthy()
  })

  it('en error muestra Reintentar y reintenta al pulsarlo', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('offline'))
    vi.stubGlobal('fetch', fetchMock)
    const store = new SegmentDraftStore()
    render(<AutosaveStatus drafts={store} />)

    act(() => {
      store.edit(SEG, 'nuevo')
      store.flush('s1')
    })
    await screen.findByText(/Error al guardar/)
    expect(fetchMock).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await screen.findByText(/Error al guardar/)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
