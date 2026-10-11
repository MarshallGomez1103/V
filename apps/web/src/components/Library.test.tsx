import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { LibraryItem } from '../api/library'
import type { LibraryState } from '../hooks/useLibrary'
import { Library } from './Library'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const item = (over: Partial<LibraryItem> & { project_id: string; name: string }): LibraryItem => ({
  created_at: '2026-10-01T10:00:00Z',
  media: { media_asset_id: 'm-' + over.project_id, filename: 'a.wav', duration_ms: 6_420_000 },
  latest_job: {
    id: 'job-' + over.project_id,
    state: 'COMPLETED',
    transcript_id: 't-' + over.project_id,
    model_id: 'turbo',
    created_at: '2026-10-01T10:00:00Z',
  },
  speaker_count: 3,
  segment_count: 1312,
  ...over,
})

const ITEMS: LibraryItem[] = [
  item({ project_id: 'p1', name: 'Clase de cálculo' }),
  item({ project_id: 'p2', name: 'Entrevista', created_at: '2026-10-02T10:00:00Z', speaker_count: 2 }),
  item({ project_id: 'p3', name: 'Sin trabajo', latest_job: null, speaker_count: null }),
]

function renderLibrary(state: LibraryState, handlers: Partial<Parameters<typeof Library>[0]> = {}) {
  const onReload = vi.fn()
  const onOpen = vi.fn()
  const onNew = vi.fn()
  render(<Library state={state} onReload={onReload} onOpen={onOpen} onNew={onNew} {...handlers} />)
  return { onReload, onOpen, onNew }
}

describe('Library', () => {
  it('muestra nombre, fecha, duración, estado y hablantes de cada transcripción', () => {
    renderLibrary({ phase: 'ready', items: ITEMS })
    const table = screen.getByRole('table', { name: 'Transcripciones guardadas' })
    expect(within(table).getByText('Clase de cálculo')).toBeDefined()
    expect(within(table).getAllByText('1:47:00').length).toBe(3)
    expect(within(table).getAllByText('Transcripción completada').length).toBe(2)
    expect(within(table).getByText('Sin transcribir')).toBeDefined()
    expect(screen.getByText('3 transcripciones')).toBeDefined()
  })

  it('el nombre es un enlace a #/t/<job> y Abrir avisa; sin trabajo no se puede abrir', () => {
    const { onOpen } = renderLibrary({ phase: 'ready', items: ITEMS })
    const link = screen.getByRole('link', { name: 'Clase de cálculo' })
    expect(link.getAttribute('href')).toBe('#/t/job-p1')

    fireEvent.click(screen.getByRole('button', { name: 'Abrir Entrevista' }))
    expect(onOpen).toHaveBeenCalledWith(ITEMS[1])
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Abrir Sin trabajo' }).disabled).toBe(true)
  })

  it('busca por nombre y dice cuando nada coincide', () => {
    renderLibrary({ phase: 'ready', items: ITEMS })
    const search = screen.getByRole('searchbox', { name: 'Buscar transcripciones' })
    fireEvent.change(search, { target: { value: 'entre' } })
    expect(screen.queryByText('Clase de cálculo')).toBeNull()
    expect(screen.getByText('Entrevista')).toBeDefined()

    fireEvent.change(search, { target: { value: 'zzz' } })
    expect(screen.getByText('Ninguna transcripción se llama «zzz».')).toBeDefined()
  })

  it('renombra con un modal y recarga; rechaza nombres vacíos', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response('{}', { status: 200 })))
    vi.stubGlobal('fetch', fetchMock)
    const { onReload } = renderLibrary({ phase: 'ready', items: ITEMS })

    fireEvent.click(screen.getByRole('button', { name: 'Renombrar Entrevista' }))
    const dialog = await screen.findByRole('dialog', { name: 'Renombrar transcripción' })
    const input = within(dialog).getByRole('textbox', { name: 'Nombre' })
    fireEvent.change(input, { target: { value: '   ' } })
    expect(within(dialog).getByRole<HTMLButtonElement>('button', { name: 'Guardar nombre' }).disabled).toBe(true)

    fireEvent.change(input, { target: { value: '  Entrevista final ' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar nombre' }))
    await waitFor(() => {
      expect(onReload).toHaveBeenCalledTimes(1)
    })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/projects/p2')
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(init.body as string)).toEqual({ name: 'Entrevista final' })
  })

  it('muestra el error del servidor al renombrar', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: { code: 'project_name_invalid', message: 'x' } }), {
            status: 422,
          }),
        ),
      ),
    )
    renderLibrary({ phase: 'ready', items: ITEMS })
    fireEvent.click(screen.getByRole('button', { name: 'Renombrar Entrevista' }))
    const dialog = await screen.findByRole('dialog', { name: 'Renombrar transcripción' })
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Nombre' }), { target: { value: 'Otro' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar nombre' }))
    expect(await within(dialog).findByText('El nombre del proyecto no es válido.')).toBeDefined()
  })

  it('eliminar explica qué se borra y envía DELETE con su cabecera', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })))
    vi.stubGlobal('fetch', fetchMock)
    const { onReload } = renderLibrary({ phase: 'ready', items: ITEMS })

    fireEvent.click(screen.getByRole('button', { name: 'Eliminar Entrevista' }))
    const dialog = await screen.findByRole('dialog', { name: 'Eliminar «Entrevista»' })
    expect(within(dialog).getByText(/copia del audio que V guardó/)).toBeDefined()
    expect(within(dialog).getByText(/Tu archivo original, el que elegiste desde tu equipo, no se toca/)).toBeDefined()
    expect(fetchMock).not.toHaveBeenCalled()

    fireEvent.click(within(dialog).getByRole('button', { name: 'Eliminar para siempre' }))
    await waitFor(() => {
      expect(onReload).toHaveBeenCalledTimes(1)
    })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/projects/p2')
    expect(init.method).toBe('DELETE')
    expect((init.headers as Record<string, string>)['X-VOZ-Action']).toBe('delete-project')
  })

  it('un proyecto con trabajo en curso no se elimina: explica por qué', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: { code: 'project_busy', message: 'x' } }), {
            status: 409,
          }),
        ),
      ),
    )
    const { onReload } = renderLibrary({ phase: 'ready', items: ITEMS })
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar Entrevista' }))
    const dialog = await screen.findByRole('dialog', { name: 'Eliminar «Entrevista»' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Eliminar para siempre' }))
    expect(await within(dialog).findByText(/Hay una transcripción en curso en este proyecto/)).toBeDefined()
    expect(onReload).not.toHaveBeenCalled()
  })

  it('estados de carga, error con reintento y vacío con «Nueva transcripción»', () => {
    const { onReload, onNew } = renderLibrary({ phase: 'error', message: 'sin red' })
    expect(screen.getByText('No se pudieron consultar las transcripciones')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(onReload).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Nueva transcripción' }))
    expect(onNew).toHaveBeenCalledTimes(1)
    cleanup()

    renderLibrary({ phase: 'loading' })
    expect(screen.getByText('Cargando las transcripciones…')).toBeDefined()
    cleanup()

    renderLibrary({ phase: 'ready', items: [] })
    expect(screen.getByText(/todavía no hay transcripciones/i)).toBeDefined()
  })
})
