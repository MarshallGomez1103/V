import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createPlayhead } from '../lib/playhead'
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

  it('oculta los hablantes sin segmentos y lo cuenta', async () => {
    stubApi({
      [LIST]: () => ({
        status: 200,
        body: { speakers: [ANA, BETO, { id: 'c', name: 'Cata', color: '#000000', segment_count: 0 }] },
      }),
    })
    render(<SpeakersPanel transcriptId="t1" />)

    await screen.findByLabelText('Nombre de Ana')
    expect(screen.queryByLabelText('Nombre de Cata')).toBeNull()
    expect(screen.getByText('1 hablante sin segmentos no se muestra.')).toBeTruthy()
  })

  it('fusiona el par elegido, no solo el primero', async () => {
    const GINA = { id: 'g', name: 'Gina', color: '#ff0000', segment_count: 4 }
    const post = vi.fn((init: RequestInit) => {
      void init
      return { status: 200, body: { speaker: GINA } }
    })
    stubApi({
      [LIST]: () => ({ status: 200, body: { speakers: [ANA, BETO, GINA] } }),
      'POST /api/speakers/b/merge': post,
    })
    render(<SpeakersPanel transcriptId="t1" />)
    await screen.findByLabelText('Nombre de Ana')

    fireEvent.change(screen.getByLabelText('Fusionar a'), { target: { value: 'b' } })
    fireEvent.change(screen.getByLabelText('dentro de'), { target: { value: 'g' } })
    fireEvent.click(screen.getByRole('button', { name: 'Fusionar' }))
    expect(screen.getByText(/¿Fusionar «Beto» en «Gina»\?/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Sí, fusionar' }))

    await waitFor(() => {
      expect(post).toHaveBeenCalled()
    })
    expect(post.mock.calls[0]?.[0].body).toBe(JSON.stringify({ into: 'g' }))
  })

  it('con un solo hablante no ofrece fusionar', async () => {
    stubApi({ [LIST]: () => ({ status: 200, body: { speakers: [ANA] } }) })
    render(<SpeakersPanel transcriptId="t1" />)
    await screen.findByLabelText('Nombre de Ana')
    expect(screen.queryByRole('button', { name: 'Fusionar' })).toBeNull()
  })

  it('mientras se calculan dice que se están identificando, no que no hay', async () => {
    stubApi({ [LIST]: () => ({ status: 200, body: { speakers: [] } }) })
    render(<SpeakersPanel transcriptId="t1" pending />)
    expect(await screen.findByText('Identificando hablantes…')).toBeTruthy()
    expect(screen.queryByText('Esta transcripción no tiene hablantes.')).toBeNull()
  })

  it('un fallo de carga ofrece reintentar', async () => {
    let fail = true
    stubApi({
      [LIST]: () =>
        fail
          ? { status: 500, body: { detail: { code: 'boom', message: 'x' } } }
          : { status: 200, body: { speakers: [ANA] } },
    })
    render(<SpeakersPanel transcriptId="t1" />)

    expect(await screen.findByRole('alert')).toBeTruthy()
    fail = false
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByLabelText('Nombre de Ana')).toBeTruthy()
  })
})

describe('SpeakersPanel: tiempo de habla, filtro, saltos y muestra', () => {
  const segs = [
    { id: 's1', start_ms: 0, end_ms: 6000, speaker_id: 'a' },
    { id: 's2', start_ms: 6000, end_ms: 8000, speaker_id: 'b' },
    { id: 's3', start_ms: 8000, end_ms: 12_000, speaker_id: 'a' },
  ]

  function setup(extra: Record<string, unknown> = {}) {
    stubApi({ [LIST]: () => ({ status: 200, body: { speakers: [ANA, BETO] } }) })
    const handlers = {
      onFilter: vi.fn(),
      onJump: vi.fn(),
      onSample: vi.fn(),
    }
    const playhead = createPlayhead()
    render(
      <SpeakersPanel
        transcriptId="t1"
        segments={segs}
        playhead={playhead}
        filterId={null}
        {...handlers}
        {...extra}
      />,
    )
    return { ...handlers, playhead }
  }

  it('muestra el tiempo de habla y el porcentaje calculados de los segmentos', async () => {
    setup()
    await screen.findByLabelText('Nombre de Ana')
    expect(screen.getByText('0:10 · 83 %')).toBeTruthy()
    expect(screen.getByText('0:02 · 17 %')).toBeTruthy()
  })

  it('prefiere talk_ms del servidor cuando viene', async () => {
    stubApi({
      [LIST]: () => ({
        status: 200,
        body: { speakers: [{ ...ANA, talk_ms: 30_000, first_ms: 0 }, { ...BETO, talk_ms: 10_000, first_ms: 6000 }] },
      }),
    })
    render(<SpeakersPanel transcriptId="t1" segments={[]} onFilter={vi.fn()} />)
    expect(await screen.findByText('0:30 · 75 %')).toBeTruthy()
    expect(screen.getByText('0:10 · 25 %')).toBeTruthy()
  })

  it('filtra por hablante y lo quita al volver a pulsar', async () => {
    const { onFilter } = setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Ver solo a Ana en la transcripción' }))
    expect(onFilter).toHaveBeenCalledWith('a')
    cleanup()
    const second = setup({ filterId: 'a' })
    fireEvent.click(await screen.findAllByRole('button', { name: 'Mostrar a todos en la transcripción' }).then((all) => all[0] as HTMLElement))
    expect(second.onFilter).toHaveBeenCalledWith(null)
  })

  it('salta a la intervención siguiente y anterior según la posición del audio', async () => {
    const { onJump, playhead } = setup()
    playhead.set(1000)
    fireEvent.click(await screen.findByRole('button', { name: 'Intervención siguiente de Ana' }))
    expect(onJump).toHaveBeenLastCalledWith({ start_ms: 8000, end_ms: 12_000, segment_id: 's3' })

    playhead.set(9000)
    fireEvent.click(screen.getByRole('button', { name: 'Intervención anterior de Ana' }))
    expect(onJump).toHaveBeenLastCalledWith({ start_ms: 0, end_ms: 6000, segment_id: 's1' })
  })

  it('escuchar muestra entrega el segmento más largo del hablante', async () => {
    const { onSample } = setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Escuchar una muestra de Ana' }))
    expect(onSample).toHaveBeenCalledWith({ start_ms: 0, end_ms: 6000, segment_id: 's1' })
  })
})

describe('SpeakersPanel: recalcular hablantes', () => {
  it('pide cuántos hablantes hay y llama a onRecalculate', async () => {
    stubApi({ [LIST]: () => ({ status: 200, body: { speakers: [ANA, BETO] } }) })
    const onRecalculate = vi.fn(() => Promise.resolve())
    render(
      <SpeakersPanel
        transcriptId="t1"
        onRecalculate={onRecalculate}
        recalc={{ phase: 'idle', pct: null, error: null }}
      />,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Recalcular hablantes' }))
    const dialog = await screen.findByRole('dialog', { name: 'Recalcular hablantes' })
    fireEvent.click(within(dialog).getByRole('tab', { name: 'Exacto' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Recalcular' }))

    await waitFor(() => {
      expect(onRecalculate).toHaveBeenCalledWith({ exact: 2 })
    })
  })

  it('si falta el modelo lo explica y ofrece ir a Modelos', async () => {
    stubApi({ [LIST]: () => ({ status: 200, body: { speakers: [ANA] } }) })
    const onOpenModels = vi.fn()
    const err = Object.assign(new Error('Falta el modelo de hablantes.'), { code: 'diarization_models_missing' })
    render(
      <SpeakersPanel
        transcriptId="t1"
        onRecalculate={() => Promise.reject(err)}
        onOpenModels={onOpenModels}
      />,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Recalcular hablantes' }))
    const dialog = await screen.findByRole('dialog', { name: 'Recalcular hablantes' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Recalcular' }))
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Ir a Modelos' }))
    expect(onOpenModels).toHaveBeenCalledTimes(1)
  })

  it('mientras recalcula muestra el avance y bloquea el botón', async () => {
    stubApi({ [LIST]: () => ({ status: 200, body: { speakers: [ANA] } }) })
    render(
      <SpeakersPanel
        transcriptId="t1"
        onRecalculate={() => Promise.resolve()}
        recalc={{ phase: 'running', pct: 40, error: null }}
      />,
    )
    expect(await screen.findByText('Recalculando hablantes: 40 %')).toBeTruthy()
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Recalcular hablantes' }).disabled).toBe(true)
  })
})
