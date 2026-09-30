import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { TranscriptSegment } from '../api/jobs'
import { SegmentList } from './SegmentList'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  Reflect.deleteProperty(HTMLElement.prototype, 'scrollBy')
})

function seg(
  id: string,
  start_ms: number,
  end_ms: number,
  text: string,
): TranscriptSegment {
  return {
    id,
    start_ms,
    end_ms,
    text,
    edited: false,
    revision: 1,
    speaker_id: null,
    words: [],
  }
}

function stubFetch(body: unknown, ok = true, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(body),
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('SegmentList', () => {
  it('no hace fetch ni renderiza cuando transcriptId es null', () => {
    const fetchMock = stubFetch({ segments: [] })

    const { container } = render(<SegmentList transcriptId={null} />)

    expect(fetchMock).not.toHaveBeenCalled()
    expect(container.innerHTML).toBe('')
  })

  it('lista los segmentos en orden con marcas de tiempo mm:ss.d', async () => {
    const fetchMock = stubFetch({
      segments: [
        seg('s1', 0, 2500, 'Hola a todos.'),
        seg('s2', 2500, 65300, 'Segunda\nlínea'),
      ],
    })

    render(<SegmentList transcriptId="tr 1" />)

    const list = await screen.findByRole('list')
    const items = within(list).getAllByRole('listitem')
    expect(items.map((item) => item.querySelector('time')?.textContent)).toEqual(
      ['00:00.0 → 00:02.5', '00:02.5 → 01:05.3'],
    )
    expect(items.map((item) => item.querySelector('p')?.textContent)).toEqual(
      ['Hola a todos.', 'Segunda\nlínea'],
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/transcripts/tr%201/segments',
      expect.objectContaining({ headers: { Accept: 'application/json' } }),
    )
  })

  it('convierte la marca de tiempo en botón que llama onSeek con start_ms', async () => {
    stubFetch({
      segments: [
        seg('s1', 0, 2500, 'Hola.'),
        seg('s2', 2500, 65300, 'Segunda.'),
      ],
    })
    const onSeek = vi.fn()

    render(<SegmentList transcriptId="tr-1" onSeek={onSeek} />)

    const list = await screen.findByRole('list')
    const buttons = within(list).getAllByRole('button', {
      name: /reproducir desde/i,
    })
    expect(buttons).toHaveLength(2)
    expect(buttons[1]?.querySelector('time')?.textContent).toBe(
      '00:02.5 → 01:05.3',
    )

    fireEvent.click(buttons[1] as HTMLElement)

    expect(onSeek).toHaveBeenCalledTimes(1)
    expect(onSeek).toHaveBeenCalledWith(2500)
  })

  it('sin onSeek la marca de tiempo no es un botón', async () => {
    stubFetch({
      segments: [seg('s1', 0, 2500, 'Hola.')],
    })

    render(<SegmentList transcriptId="tr-1" />)

    const list = await screen.findByRole('list')
    expect(within(list).queryByRole('button')).toBeNull()
    expect(list.querySelector('time')).not.toBeNull()
  })

  it('muestra un estado vacío cuando no hay segmentos', async () => {
    stubFetch({ segments: [] })

    render(<SegmentList transcriptId="tr-1" />)

    expect(
      await screen.findByText(/no contiene segmentos/i),
    ).toBeDefined()
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('muestra un error seguro cuando la API falla', async () => {
    stubFetch(
      { detail: { code: 'transcript_not_found', message: 'raw' } },
      false,
      404,
    )

    render(<SegmentList transcriptId="tr-1" />)

    expect((await screen.findByRole('alert')).textContent).toBe(
      'La transcripción ya no existe.',
    )
  })

  // --- S5.11 / S5.13 / S5.15 ---

  const scrolls = () => {
    const scrollBy = vi.fn()
    Object.defineProperty(HTMLElement.prototype, 'scrollBy', {
      configurable: true,
      value: scrollBy,
    })
    // Contenedor visible entre 0 y 100 px; la fila i ocupa [200i, 200i+50].
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(
      function (this: Element) {
        const index = this.getAttribute('data-segment-index')
        const top = index === null ? 0 : Number(index) * 200
        const bottom = index === null ? 100 : top + 50
        return { top, bottom } as DOMRect
      },
    )
    return scrollBy
  }

  const timeline = [
    seg('s1', 0, 1000, 'Hola a todos.'),
    seg('s2', 1000, 2000, 'La canción de Ángel'),
    seg('s3', 3000, 4000, 'Cancion final, canción'),
  ]

  it('marca con aria-current el segmento activo y ninguno en los huecos', async () => {
    stubFetch({ segments: timeline })
    const { rerender } = render(<SegmentList transcriptId="tr-1" currentMs={1500} />)
    const items = within(await screen.findByRole('list')).getAllByRole('listitem')

    expect(items.map((item) => item.getAttribute('aria-current'))).toEqual([
      null,
      'true',
      null,
    ])

    rerender(<SegmentList transcriptId="tr-1" currentMs={2500} />)
    expect(items.some((item) => item.hasAttribute('aria-current'))).toBe(false)

    rerender(<SegmentList transcriptId="tr-1" currentMs={3000} />)
    expect(items[2]?.getAttribute('aria-current')).toBe('true')
  })

  it('sin currentMs no hay segmento activo ni botón de seguimiento', async () => {
    stubFetch({ segments: timeline })
    render(<SegmentList transcriptId="tr-1" />)
    const items = within(await screen.findByRole('list')).getAllByRole('listitem')

    expect(items.some((item) => item.hasAttribute('aria-current'))).toBe(false)
    fireEvent.wheel(screen.getByRole('region', { name: /lista de segmentos/i }))
    expect(screen.queryByRole('button', { name: /seguir reproducción/i })).toBeNull()
  })

  it('autoscroll suave al segmento activo dentro del contenedor', async () => {
    const scrollBy = scrolls()
    stubFetch({ segments: timeline })
    const { rerender } = render(<SegmentList transcriptId="tr-1" currentMs={0} />)
    await screen.findByRole('list')
    expect(scrollBy).not.toHaveBeenCalled() // fila 0 ya visible

    rerender(<SegmentList transcriptId="tr-1" currentMs={3200} />)

    // fila 2: [400, 450] frente a un contenedor [0, 100] -> baja 350 px.
    expect(scrollBy).toHaveBeenCalledTimes(1)
    expect(scrollBy).toHaveBeenCalledWith({ top: 350, behavior: 'smooth' })
  })

  it.each([
    ['rueda', (region: HTMLElement) => fireEvent.wheel(region)],
    ['táctil', (region: HTMLElement) => fireEvent.touchStart(region)],
    ['teclado', (region: HTMLElement) => fireEvent.keyDown(region, { key: 'PageDown' })],
  ])('el gesto manual (%s) pausa el autoscroll y "Seguir reproducción" lo reanuda', async (_name, gesture) => {
    const scrollBy = scrolls()
    stubFetch({ segments: timeline })
    const { rerender } = render(<SegmentList transcriptId="tr-1" currentMs={0} />)
    await screen.findByRole('list')

    gesture(screen.getByRole('region', { name: /lista de segmentos/i }))
    rerender(<SegmentList transcriptId="tr-1" currentMs={3200} />)
    expect(scrollBy).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: /seguir reproducción/i }))

    expect(scrollBy).toHaveBeenCalledWith({ top: 350, behavior: 'smooth' })
    expect(screen.queryByRole('button', { name: /seguir reproducción/i })).toBeNull()
  })

  it('enfocar un editor dentro de una fila pausa el autoscroll', async () => {
    const scrollBy = scrolls()
    stubFetch({ segments: timeline })
    const renderText = (segment: TranscriptSegment) => (
      <textarea aria-label={'Editar ' + segment.id} defaultValue={segment.text} />
    )
    const { rerender } = render(
      <SegmentList transcriptId="tr-1" currentMs={0} renderText={renderText} />,
    )
    await screen.findByRole('list')

    screen.getByLabelText('Editar s1').focus()
    rerender(
      <SegmentList transcriptId="tr-1" currentMs={3200} renderText={renderText} />,
    )

    expect(scrollBy).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /seguir reproducción/i })).toBeDefined()
  })

  it('enfocar el botón de una marca de tiempo NO pausa el autoscroll', async () => {
    const scrollBy = scrolls()
    stubFetch({ segments: timeline })
    const onSeek = vi.fn()
    const { rerender } = render(
      <SegmentList transcriptId="tr-1" currentMs={0} onSeek={onSeek} />,
    )
    await screen.findByRole('list')

    screen.getAllByRole('button', { name: /reproducir desde/i })[0]?.focus()
    rerender(<SegmentList transcriptId="tr-1" currentMs={3200} onSeek={onSeek} />)

    expect(scrollBy).toHaveBeenCalledTimes(1)
  })

  it('busca sin distinguir mayúsculas ni tildes y resalta con <mark>', async () => {
    stubFetch({ segments: timeline })
    render(<SegmentList transcriptId="tr-1" />)
    const list = await screen.findByRole('list')

    const box = screen.getByRole('searchbox', { name: /buscar en la transcripción/i })
    fireEvent.change(box, { target: { value: 'CANCION' } })

    expect(Array.from(list.querySelectorAll('mark')).map((m) => m.textContent)).toEqual(
      ['canción', 'Cancion', 'canción'],
    )
    expect(screen.getByText('1 de 3')).toBeDefined()
    expect(list.querySelectorAll('mark.is-current')).toHaveLength(1)
  })

  it('navega con botones y Enter / Shift+Enter de forma circular', async () => {
    stubFetch({ segments: timeline })
    render(<SegmentList transcriptId="tr-1" />)
    const list = await screen.findByRole('list')
    const box = screen.getByRole('searchbox')
    fireEvent.change(box, { target: { value: 'cancion' } })

    const current = () =>
      Array.from(list.querySelectorAll('mark')).findIndex((m) =>
        m.classList.contains('is-current'),
      )
    expect(current()).toBe(0)

    fireEvent.click(screen.getByRole('button', { name: /coincidencia siguiente/i }))
    expect(screen.getByText('2 de 3')).toBeDefined()
    expect(current()).toBe(1)

    fireEvent.keyDown(box, { key: 'Enter' })
    expect(screen.getByText('3 de 3')).toBeDefined()
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(screen.getByText('1 de 3')).toBeDefined()

    fireEvent.keyDown(box, { key: 'Enter', shiftKey: true })
    expect(screen.getByText('3 de 3')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: /coincidencia anterior/i }))
    expect(screen.getByText('2 de 3')).toBeDefined()
    expect(current()).toBe(1)
  })

  it('la coincidencia actual se desplaza a la vista y pausa el autoscroll', async () => {
    const scrollBy = scrolls()
    stubFetch({ segments: timeline })
    const { rerender } = render(<SegmentList transcriptId="tr-1" currentMs={0} />)
    await screen.findByRole('list')

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'final' } })

    // Coincidencia en la fila 2 -> desplaza el contenedor.
    expect(scrollBy).toHaveBeenLastCalledWith({ top: 350, behavior: 'smooth' })
    scrollBy.mockClear()

    rerender(<SegmentList transcriptId="tr-1" currentMs={1200} />)
    expect(scrollBy).not.toHaveBeenCalled() // autoscroll pausado por la búsqueda
    expect(screen.getByRole('button', { name: /seguir reproducción/i })).toBeDefined()
  })

  it('sin coincidencias avisa y deshabilita la navegación', async () => {
    stubFetch({ segments: timeline })
    render(<SegmentList transcriptId="tr-1" />)
    await screen.findByRole('list')

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'zzz' } })

    expect(screen.getByText('Sin coincidencias')).toBeDefined()
    expect(
      screen.getByRole<HTMLButtonElement>('button', { name: /coincidencia siguiente/i })
        .disabled,
    ).toBe(true)
  })

  it('renderText sustituye el texto y recibe la consulta', async () => {
    stubFetch({ segments: timeline })
    const renderText = vi.fn((segment: TranscriptSegment, query: string) => (
      <span data-testid="custom">{segment.id + ':' + query}</span>
    ))
    render(<SegmentList transcriptId="tr-1" renderText={renderText} />)
    await screen.findByRole('list')

    expect(screen.getAllByTestId('custom').map((n) => n.textContent)).toEqual([
      's1:',
      's2:',
      's3:',
    ])
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: ' hola ' } })
    expect(screen.getAllByTestId('custom')[0]?.textContent).toBe('s1:hola')
  })

  it('renderiza 10.000 segmentos y un cambio de currentMs solo re-renderiza 2 filas', async () => {
    const many = Array.from({ length: 10_000 }, (_, i) =>
      seg('s' + i, i * 1000, i * 1000 + 900, 'segmento ' + i),
    )
    stubFetch({ segments: many })
    const renderText = vi.fn((segment: TranscriptSegment) => segment.text)
    const { rerender } = render(
      <SegmentList transcriptId="big" currentMs={5000} renderText={renderText} />,
    )

    const list = await screen.findByRole('list', undefined, { timeout: 15_000 })
    expect(list.children).toHaveLength(10_000)
    expect(list.querySelector('[aria-current="true"]')?.textContent).toContain(
      'segmento 5',
    )
    expect(list.children[0]?.className).toBe('segment-row')
    expect(renderText).toHaveBeenCalledTimes(10_000)

    renderText.mockClear()
    rerender(<SegmentList transcriptId="big" currentMs={6100} renderText={renderText} />)

    // Salen de escena la fila 5 y entra la 6: solo esas dos se re-renderizan.
    expect(renderText).toHaveBeenCalledTimes(2)
    expect(list.querySelector('[aria-current="true"]')?.textContent).toContain(
      'segmento 6',
    )

    // Un cambio dentro del mismo segmento no toca ninguna fila.
    renderText.mockClear()
    rerender(<SegmentList transcriptId="big" currentMs={6200} renderText={renderText} />)
    expect(renderText).not.toHaveBeenCalled()
  }, 30_000)
})
