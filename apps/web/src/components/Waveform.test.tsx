import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Waveform } from './Waveform'

const PEAKS = Array.from({ length: 50 }, (_, i): [number, number] => [
  -(i % 10) / 10,
  (i % 10) / 10,
])

function payload(durationMs = 10_000) {
  return {
    media_asset_id: 'a1',
    duration_ms: durationMs,
    buckets: PEAKS.length,
    peaks: PEAKS,
  }
}

function stubFetch(body: unknown, status = 200) {
  const fetchMock = vi
    .fn<(url: string, init?: RequestInit) => Promise<Response>>()
    .mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
      text: () => Promise.resolve(JSON.stringify(body)),
    } as Response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

beforeEach(() => {
  // jsdom no implementa canvas: devuelve null como los navegadores sin soporte.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

async function renderReady(props: { currentMs?: number; onSeek?: () => void } = {}) {
  stubFetch(payload())
  const onSeek = props.onSeek ?? vi.fn()
  const view = render(
    <Waveform mediaAssetId="a1" currentMs={props.currentMs ?? 0} onSeek={onSeek} />,
  )
  await screen.findByRole('slider', { name: /Posición en la grabación/ })
  return { ...view, onSeek }
}

function content(container: HTMLElement): HTMLElement {
  const element = container.querySelector<HTMLElement>('.waveform__content')
  if (!element) {
    throw new Error('missing content')
  }
  return element
}

function playhead(container: HTMLElement): HTMLElement {
  const element = container.querySelector<HTMLElement>('.waveform__playhead')
  if (!element) {
    throw new Error('missing playhead')
  }
  return element
}

describe('Waveform: carga', () => {
  it('muestra cargando y luego el waveform pidiendo los peaks del asset', async () => {
    const fetchMock = stubFetch(payload())

    render(<Waveform mediaAssetId="a 1" currentMs={0} onSeek={vi.fn()} />)

    expect(screen.getByRole('status').textContent).toContain('Cargando')
    await screen.findByRole('region', { name: 'Forma de onda' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] ?? []
    expect(url).toBe('/api/media/a%201/peaks?buckets=4000')
    expect(init?.signal).toBeInstanceOf(AbortSignal)
    expect(screen.queryByText(/Cargando/)).toBeNull()
  })

  it('muestra un error seguro en español si el backend falla', async () => {
    stubFetch(
      { detail: { code: 'waveform_unavailable', message: 'boom /home/x' } },
      500,
    )

    render(<Waveform mediaAssetId="a1" currentMs={0} onSeek={vi.fn()} />)

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain(
      'No se pudo calcular la forma de onda de este audio.',
    )
    expect(alert.textContent).not.toContain('/home')
  })

  it('muestra un error si la respuesta es inválida', async () => {
    stubFetch({ peaks: 'nope' })

    render(<Waveform mediaAssetId="a1" currentMs={0} onSeek={vi.fn()} />)

    expect((await screen.findByRole('alert')).textContent).toContain('inválida')
  })

  it('muestra un error de red', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))

    render(<Waveform mediaAssetId="a1" currentMs={0} onSeek={vi.fn()} />)

    expect((await screen.findByRole('alert')).textContent).toContain('conectar')
  })

  it('aborta la petición al desmontar y al cambiar de asset', async () => {
    const fetchMock = stubFetch(payload())
    const { rerender, unmount } = render(
      <Waveform mediaAssetId="a1" currentMs={0} onSeek={vi.fn()} />,
    )
    await screen.findByRole('region')
    const first = fetchMock.mock.calls[0]?.[1]?.signal

    rerender(<Waveform mediaAssetId="a2" currentMs={0} onSeek={vi.fn()} />)
    expect(first?.aborted).toBe(true)
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2)
    })
    const second = fetchMock.mock.calls[1]?.[1]?.signal
    unmount()
    expect(second?.aborted).toBe(true)
  })
})

describe('Waveform: dibujo, playhead y clic', () => {
  it('dibuja las columnas en el canvas cuando hay contexto 2d', async () => {
    const fillRect = vi.fn()
    const context = {
      setTransform: vi.fn(),
      clearRect: vi.fn(),
      fillRect,
      fillStyle: '',
    }
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
      context as unknown as CanvasRenderingContext2D,
    )

    await renderReady()

    expect(fillRect).toHaveBeenCalled()
    expect(context.fillStyle).toBeTruthy()
  })

  it('posiciona el playhead según currentMs', async () => {
    const { container, rerender } = await renderReady({ currentMs: 2500 })
    // Sin medida en jsdom: vista de reserva de 640 px; 2.5 s de 10 s = 160 px.
    expect(playhead(container).style.left).toBe('160px')

    rerender(<Waveform mediaAssetId="a1" currentMs={5000} onSeek={vi.fn()} />)
    expect(playhead(container).style.left).toBe('320px')
  })

  it('un clic llama a onSeek con el instante correspondiente', async () => {
    const { container, onSeek } = await renderReady()

    fireEvent.click(content(container), { clientX: 320 })

    expect(onSeek).toHaveBeenCalledWith(5000)
  })

  it('el clic se acota a los límites de la grabación', async () => {
    const { container, onSeek } = await renderReady()

    fireEvent.click(content(container), { clientX: 5000 })
    fireEvent.click(content(container), { clientX: -40 })

    expect(onSeek).toHaveBeenNthCalledWith(1, 10_000)
    expect(onSeek).toHaveBeenNthCalledWith(2, 0)
  })

  it('el clic con zoom apunta al instante ampliado', async () => {
    const { container, onSeek } = await renderReady()
    fireEvent.click(screen.getByRole('button', { name: 'Acercar' }))
    fireEvent.click(screen.getByRole('button', { name: 'Acercar' }))

    // 4x -> 2560 px de contenido; x=640 es el 25 %.
    fireEvent.click(content(container), { clientX: 640 })

    expect(onSeek).toHaveBeenLastCalledWith(2500)
  })
})

describe('Waveform: zoom (S5.14)', () => {
  it('Acercar y Alejar cambian el zoom y respetan los límites 1x-32x', async () => {
    await renderReady()
    const zoomIn = screen.getByRole('button', { name: 'Acercar' })
    const zoomOut = screen.getByRole('button', { name: 'Alejar' })
    const range = screen.getByRole<HTMLInputElement>('slider', {
      name: 'Zoom de la forma de onda',
    })
    expect(zoomOut).toHaveProperty('disabled', true)
    expect(range.min).toBe('1')
    expect(range.max).toBe('32')

    for (let i = 0; i < 6; i += 1) {
      fireEvent.click(zoomIn)
    }
    expect(range.value).toBe('32')
    expect(screen.getByText('32x')).toBeTruthy()
    expect(zoomIn).toHaveProperty('disabled', true)

    fireEvent.click(zoomOut)
    expect(range.value).toBe('16')
    expect(zoomIn).toHaveProperty('disabled', false)
  })

  it('el control deslizante fija el zoom y ensancha el contenido', async () => {
    const { container } = await renderReady()

    fireEvent.change(
      screen.getByRole('slider', { name: 'Zoom de la forma de onda' }),
      { target: { value: '8' } },
    )

    expect(screen.getByText('8x')).toBeTruthy()
    expect(content(container).style.width).toBe('5120px')
  })

  it('al cambiar el zoom el playhead sigue visible en la vista', async () => {
    const { container } = await renderReady({ currentMs: 5000 })
    const scroller = container.querySelector<HTMLElement>('.waveform__scroller')

    fireEvent.click(screen.getByRole('button', { name: 'Acercar' }))
    fireEvent.click(screen.getByRole('button', { name: 'Acercar' }))

    // Playhead a mitad de la vista (320 px) y ahora en 1280 px de 2560.
    const left = parseFloat(playhead(container).style.left)
    expect(left).toBe(1280)
    const scrollLeft = scroller?.scrollLeft ?? -1
    expect(scrollLeft).toBe(960)
    expect(left).toBeGreaterThanOrEqual(scrollLeft)
    expect(left).toBeLessThanOrEqual(scrollLeft + 640)
  })

  it('sigue la reproducción cuando el playhead sale por la derecha', async () => {
    const { container, rerender } = await renderReady({ currentMs: 0 })
    const scroller = container.querySelector<HTMLElement>('.waveform__scroller')
    fireEvent.click(screen.getByRole('button', { name: 'Acercar' }))
    fireEvent.click(screen.getByRole('button', { name: 'Acercar' }))
    expect(scroller?.scrollLeft).toBe(0)

    rerender(<Waveform mediaAssetId="a1" currentMs={5000} onSeek={vi.fn()} />)

    const left = parseFloat(playhead(container).style.left)
    const scrollLeft = scroller?.scrollLeft ?? -1
    expect(left).toBe(1280)
    expect(scrollLeft).toBe(960)
  })

  it('no arrastra la vista si el usuario se alejó del playhead a mano', async () => {
    const { container, rerender } = await renderReady({ currentMs: 0 })
    const scroller = container.querySelector<HTMLElement>('.waveform__scroller')
    fireEvent.click(screen.getByRole('button', { name: 'Acercar' }))
    fireEvent.click(screen.getByRole('button', { name: 'Acercar' }))
    if (scroller) {
      scroller.scrollLeft = 1800
      fireEvent.scroll(scroller)
    }

    rerender(<Waveform mediaAssetId="a1" currentMs={200} onSeek={vi.fn()} />)

    expect(scroller?.scrollLeft).toBe(1800)
  })
})

describe('Waveform: teclado', () => {
  it('el waveform es enfocable y expone el progreso', async () => {
    await renderReady({ currentMs: 65_000 })
    const slider = screen.getByRole('slider', { name: /Posición en la grabación/ })

    expect(slider.getAttribute('tabindex')).toBe('0')
    expect(slider.getAttribute('aria-valuenow')).toBe('10000')
    expect(slider.getAttribute('aria-valuemax')).toBe('10000')
    expect(slider.getAttribute('aria-valuetext')).toBe('1:05 de 0:10')
  })

  it('flechas izquierda y derecha buscan ±5 s', async () => {
    const onSeek = vi.fn()
    stubFetch(payload(60_000))
    render(<Waveform mediaAssetId="a1" currentMs={20_000} onSeek={onSeek} />)
    const slider = await screen.findByRole('slider', {
      name: /Posición en la grabación/,
    })

    fireEvent.keyDown(slider, { key: 'ArrowRight' })
    fireEvent.keyDown(slider, { key: 'ArrowLeft' })

    expect(onSeek).toHaveBeenNthCalledWith(1, 25_000)
    expect(onSeek).toHaveBeenNthCalledWith(2, 15_000)
  })

  it('los saltos se acotan a 0 y a la duración y otras teclas se ignoran', async () => {
    const onSeek = vi.fn()
    stubFetch(payload(10_000))
    const { rerender } = render(
      <Waveform mediaAssetId="a1" currentMs={2000} onSeek={onSeek} />,
    )
    const slider = await screen.findByRole('slider', {
      name: /Posición en la grabación/,
    })

    fireEvent.keyDown(slider, { key: 'ArrowLeft' })
    fireEvent.keyDown(slider, { key: 'Enter' })
    rerender(<Waveform mediaAssetId="a1" currentMs={9000} onSeek={onSeek} />)
    fireEvent.keyDown(slider, { key: 'ArrowRight' })

    expect(onSeek).toHaveBeenCalledTimes(2)
    expect(onSeek).toHaveBeenNthCalledWith(1, 0)
    expect(onSeek).toHaveBeenNthCalledWith(2, 10_000)
  })

  it('previene el scroll nativo de las flechas', async () => {
    await renderReady()
    const slider = screen.getByRole('slider', { name: /Posición en la grabación/ })

    const notPrevented = fireEvent.keyDown(slider, { key: 'ArrowRight' })

    expect(notPrevented).toBe(false)
  })
})

it('no lanza si el desmontaje llega antes de la respuesta', () => {
  stubFetch(payload())
  const { unmount } = render(
    <Waveform mediaAssetId="a1" currentMs={0} onSeek={vi.fn()} />,
  )

  expect(() => {
    act(() => {
      unmount()
    })
  }).not.toThrow()
})
