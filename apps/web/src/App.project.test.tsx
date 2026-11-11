/** Cableado de la pantalla de proyecto en `App`: ruta, acción de la biblioteca y recarga al volver. */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

const ITEM = {
  project_id: 'p1',
  name: 'Clase',
  created_at: '2026-10-01T10:00:00Z',
  media: { media_asset_id: 'm1', filename: 'a.wav', duration_ms: 60_000 },
  latest_job: null,
  speaker_count: null,
  segment_count: null,
}

const RECORDING = {
  media_asset_id: 'm1',
  filename: 'a.wav',
  media_type: 'audio',
  duration_ms: 60_000,
  created_at: '2026-10-01T10:00:00Z',
  latest_job: null,
}

function stubApi() {
  const fetchMock = vi.fn((url: string) => {
    const body = url.includes('/api/health')
      ? { status: 'ok', service: 'voz' }
      : url.endsWith('/recordings')
        ? { recordings: [RECORDING] }
        : url === '/api/library'
          ? { items: [ITEM] }
          : {}
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return (suffix: string) => fetchMock.mock.calls.filter(([url]) => url === suffix).length
}

describe('App · proyecto', () => {
  beforeEach(() => {
    window.location.hash = ''
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('#/p/<id> monta la pantalla del proyecto con sus grabaciones', async () => {
    window.location.hash = '#/p/p1'
    const calls = stubApi()
    render(<App />)

    expect(await screen.findByRole('table', { name: 'Grabaciones del proyecto' })).toBeDefined()
    expect(screen.getByRole('heading', { level: 1, name: 'Proyecto' })).toBeDefined()
    expect(calls('/api/projects/p1/recordings')).toBe(1)
  })

  it('«Abrir proyecto» navega a #/p/<id> y al volver a Inicio se recarga la biblioteca', async () => {
    const calls = stubApi()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: 'Abrir proyecto Clase' }))
    expect(window.location.hash).toBe('#/p/p1')
    expect(await screen.findByRole('table', { name: 'Grabaciones del proyecto' })).toBeDefined()
    expect(screen.queryByRole('table', { name: 'Transcripciones guardadas' })).toBeNull()
    const before = calls('/api/library')

    act(() => {
      window.location.hash = '#/'
    })
    expect(await screen.findByRole('table', { name: 'Transcripciones guardadas' })).toBeDefined()
    await vi.waitFor(() => {
      expect(calls('/api/library')).toBeGreaterThan(before)
    })
    expect(screen.queryByRole('table', { name: 'Grabaciones del proyecto' })).toBeNull()
  })
})
