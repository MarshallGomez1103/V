import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SpeakersPanel } from './SpeakersPanel'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const ANA = { id: 'a', name: 'Ana', color: '#112233', segment_count: 2 }
const BETO = { id: 'b', name: 'Beto', color: '#445566', segment_count: 1 }

type Route = (init: RequestInit) => { status: number; body: unknown }

function stubApi(routes: Record<string, Route>) {
  const fetchMock = vi.fn((url: string, init: RequestInit = {}) => {
    const route = routes[(init.method ?? 'GET') + ' ' + url]
    const { status, body } = route
      ? route(init)
      : { status: 500, body: { detail: { code: 'boom', message: 'x' } } }
    return Promise.resolve({
      ok: status < 300,
      status,
      json: () => Promise.resolve(body),
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const LIST = 'GET /api/transcripts/t1/speakers'

describe('SpeakersPanel', () => {
  it('lista hablantes con color y contador de segmentos', async () => {
    stubApi({ [LIST]: () => ({ status: 200, body: { speakers: [ANA, BETO] } }) })
    render(<SpeakersPanel transcriptId="t1" />)

    expect(await screen.findByLabelText('Nombre de Ana')).toBeTruthy()
    expect(screen.getByText('2 segmentos')).toBeTruthy()
    expect(screen.getByText('1 segmento')).toBeTruthy()
    expect(
      screen.getByLabelText<HTMLInputElement>('Color de Ana').value,
    ).toBe('#112233')
  })

  it('renombra al salir del campo y avisa con onChanged', async () => {
    const patch = vi.fn((init: RequestInit) => {
      void init
      return { status: 200, body: { ...ANA, name: 'Ana María' } }
    })
    stubApi({
      [LIST]: () => ({ status: 200, body: { speakers: [ANA, BETO] } }),
      'PATCH /api/speakers/a': patch,
    })
    const onChanged = vi.fn()
    render(<SpeakersPanel transcriptId="t1" onChanged={onChanged} />)

    const input = await screen.findByLabelText('Nombre de Ana')
    fireEvent.change(input, { target: { value: '  Ana María ' } })
    fireEvent.blur(input)

    await waitFor(() => {
      expect(onChanged).toHaveBeenCalledTimes(1)
    })
    expect(patch.mock.calls[0]?.[0].body).toBe(JSON.stringify({ name: 'Ana María' }))
    expect(
      screen.getByLabelText<HTMLInputElement>('Nombre de Ana María').value,
    ).toBe('Ana María')
  })

  it('no llama a la API si el nombre no cambió', async () => {
    const fetchMock = stubApi({
      [LIST]: () => ({ status: 200, body: { speakers: [ANA] } }),
    })
    render(<SpeakersPanel transcriptId="t1" />)

    const input = await screen.findByLabelText('Nombre de Ana')
    fireEvent.blur(input)

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('cambia el color con PATCH', async () => {
    const patch = vi.fn((init: RequestInit) => {
      void init
      return { status: 200, body: { ...ANA, color: '#abcdef' } }
    })
    stubApi({
      [LIST]: () => ({ status: 200, body: { speakers: [ANA] } }),
      'PATCH /api/speakers/a': patch,
    })
    render(<SpeakersPanel transcriptId="t1" />)

    fireEvent.change(await screen.findByLabelText('Color de Ana'), {
      target: { value: '#abcdef' },
    })

    await waitFor(() => {
      expect(patch).toHaveBeenCalled()
    })
    expect(patch.mock.calls[0]?.[0].body).toBe(JSON.stringify({ color: '#abcdef' }))
  })

  it('fusiona solo tras confirmar y recarga la lista', async () => {
    let merged = false
    const post = vi.fn((init: RequestInit) => {
      void init
      merged = true
      return { status: 200, body: { speaker: { ...BETO, segment_count: 3 } } }
    })
    stubApi({
      [LIST]: () => ({
        status: 200,
        body: { speakers: merged ? [{ ...BETO, segment_count: 3 }] : [ANA, BETO] },
      }),
      'POST /api/speakers/a/merge': post,
    })
    const onChanged = vi.fn()
    render(<SpeakersPanel transcriptId="t1" onChanged={onChanged} />)
    await screen.findByLabelText('Nombre de Ana')

    fireEvent.click(screen.getAllByRole('button', { name: 'Fusionar' })[0]!)
    expect(post).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog', { name: 'Fusionar hablantes' })).toBeTruthy()
    expect(screen.getByText(/¿Fusionar «Ana» en «Beto»\?/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Sí, fusionar' }))

    await waitFor(() => {
      expect(screen.queryByLabelText('Nombre de Ana')).toBeNull()
    })
    expect(post.mock.calls[0]?.[0].body).toBe(JSON.stringify({ into: 'b' }))
    expect(screen.getByText('3 segmentos')).toBeTruthy()
    expect(onChanged).toHaveBeenCalledTimes(1)
  })

  it('cancelar la confirmación no fusiona', async () => {
    const fetchMock = stubApi({
      [LIST]: () => ({ status: 200, body: { speakers: [ANA, BETO] } }),
    })
    render(<SpeakersPanel transcriptId="t1" />)
    await screen.findByLabelText('Nombre de Ana')

    fireEvent.click(screen.getAllByRole('button', { name: 'Fusionar' })[0]!)
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(screen.queryByText(/¿Fusionar/)).toBeNull()
  })

  it('un error de la API se muestra como alerta', async () => {
    stubApi({
      [LIST]: () => ({ status: 200, body: { speakers: [ANA] } }),
      'PATCH /api/speakers/a': () => ({
        status: 422,
        body: { detail: { code: 'speaker_update_invalid', message: 'x' } },
      }),
    })
    render(<SpeakersPanel transcriptId="t1" />)

    const input = await screen.findByLabelText('Nombre de Ana')
    fireEvent.change(input, { target: { value: 'Nuevo' } })
    fireEvent.blur(input)

    expect(await screen.findByText(/1 a 80 caracteres/)).toBeTruthy()
  })

  it('si no puede cargar, muestra el error', async () => {
    stubApi({
      [LIST]: () => ({
        status: 404,
        body: { detail: { code: 'transcript_not_found', message: 'x' } },
      }),
    })
    render(<SpeakersPanel transcriptId="t1" />)

    expect((await screen.findByRole('alert')).textContent).toMatch(
      /La transcripción ya no existe/,
    )
  })
})
