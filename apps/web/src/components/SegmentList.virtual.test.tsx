/** Lista virtualizada con mediciones reales simuladas: filtros y saltos a segmentos lejanos. */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { TranscriptSegment } from '../api/jobs'
import { SegmentList } from './SegmentList'

const VIEWPORT = 600
const HEIGHT = { A: 40, B: 160 } as const

/** Alturas "del navegador": dependen del hablante, como pasa con textos cortos y largos. */
function trueHeight(row: HTMLElement): number {
  return row.textContent?.includes('-B') ? HEIGHT.B : HEIGHT.A
}

class FakeResizeObserver {
  static instances: FakeResizeObserver[] = []
  readonly targets = new Set<Element>()
  constructor(private readonly callback: () => void) {
    FakeResizeObserver.instances.push(this)
  }
  // Como el real: avisa una vez al empezar a observar un elemento.
  observe(target: Element) {
    this.targets.add(target)
    queueMicrotask(this.callback)
  }
  unobserve(target: Element) {
    this.targets.delete(target)
  }
  disconnect() {
    this.targets.clear()
  }
}

function makeSegments(count: number): TranscriptSegment[] {
  return Array.from({ length: count }, (_, i) => {
    const speaker = i % 2 === 0 ? 'A' : 'B'
    return {
      id: 's' + String(i),
      start_ms: i * 1000,
      end_ms: i * 1000 + 900,
      text: 'seg-' + String(i) + '-' + speaker,
      edited: false,
      revision: 1,
      speaker_id: 'sp' + speaker,
      quality: { flags: [], avg_logprob: null },
      words: [],
    }
  })
}

function stubFetch(segments: TranscriptSegment[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({ segments }) }),
  )
}

/** Deja correr los fotogramas y microtareas que encadenan observador → medición → render. */
async function settle() {
  for (let i = 0; i < 12; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
  }
}

interface Layout {
  region: HTMLElement
  padTop: number
  padBottom: number
  rows: { index: number; height: number; top: number; text: string }[]
}

/** Lo que vería la persona: posición real de cada fila pintada y el relleno que las rodea. */
function layout(): Layout {
  const region = screen.getByRole('region', { name: /lista de segmentos/i })
  const list = region.querySelector<HTMLElement>('ol.segments')
  if (list === null) {
    throw new Error('sin lista')
  }
  const padTop = parseFloat(list.style.paddingBlockStart || '0')
  const padBottom = parseFloat(list.style.paddingBlockEnd || '0')
  let top = padTop
  const rows = [...list.querySelectorAll<HTMLElement>('[data-segment-index]')].map((row) => {
    const height = trueHeight(row)
    const entry = {
      index: Number(row.dataset.segmentIndex),
      height,
      top,
      text: row.querySelector('.segment-text')?.textContent ?? '',
    }
    top += height
    return entry
  })
  return { region, padTop, padBottom, rows }
}

function scrollTop(region: HTMLElement): number {
  return Number(region.scrollTop)
}

beforeEach(() => {
  FakeResizeObserver.instances = []
  vi.stubGlobal('ResizeObserver', FakeResizeObserver)
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockImplementation(function (this: HTMLElement) {
    return this.hasAttribute('data-segment-index') ? trueHeight(this) : 0
  })
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(function (this: HTMLElement) {
    return this.classList.contains('segments-scroll') ? VIEWPORT : 0
  })
  // El desplazamiento real: mover scrollTop y avisar con el evento scroll.
  Object.defineProperty(HTMLElement.prototype, 'scrollTo', {
    configurable: true,
    value(this: HTMLElement, options: ScrollToOptions) {
      Object.defineProperty(this, 'scrollTop', {
        configurable: true,
        writable: true,
        value: options.top ?? 0,
      })
      fireEvent.scroll(this)
    },
  })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  Reflect.deleteProperty(HTMLElement.prototype, 'scrollTo')
})

describe('SegmentList virtualizada con medición simulada', () => {
  it('cubre la vista sin filas vacías y mide con ResizeObserver', async () => {
    stubFetch(makeSegments(400))
    render(<SegmentList transcriptId="t" />)
    await screen.findByRole('list')
    await settle()

    const { rows, padTop } = layout()
    expect(FakeResizeObserver.instances.length).toBeGreaterThan(0)
    expect(rows.length).toBeGreaterThan(0)
    expect(rows.length).toBeLessThan(40)
    expect(rows.every((row) => row.text.trim() !== '')).toBe(true)
    // Empieza arriba y las filas pintadas llenan la vista.
    expect(padTop).toBe(0)
    expect(rows.at(-1)!.top + rows.at(-1)!.height).toBeGreaterThanOrEqual(VIEWPORT)
  })

  it('al filtrar por hablante la lista queda completa y su altura total coincide con la real', async () => {
    const all = makeSegments(400)
    stubFetch(all)
    const speakers = [
      { id: 'spA', name: 'Ana', color: '#111111', segment_count: 200 },
      { id: 'spB', name: 'Beto', color: '#222222', segment_count: 200 },
    ]
    const { rerender } = render(<SegmentList transcriptId="t" speakers={speakers} />)
    await screen.findByRole('list')
    await settle()

    rerender(<SegmentList transcriptId="t" speakers={speakers} speakerFilter="spB" />)
    await settle()

    const { rows, padTop, padBottom } = layout()
    expect(rows.length).toBeGreaterThan(0)
    expect(rows.every((row) => row.text.endsWith('-B'))).toBe(true)
    expect(rows.every((row, i) => i === 0 || row.index === rows[i - 1]!.index + 1)).toBe(true)
    // Todas las filas del hablante B miden lo mismo: el total estimado debe ser el real.
    const modelled = padTop + rows.reduce((sum, row) => sum + row.height, 0) + padBottom
    expect(modelled).toBe(200 * HEIGHT.B)
  })

  it('tras filtrar y quitar el filtro la vista sigue cubierta, contigua y con texto', async () => {
    const all = makeSegments(400)
    stubFetch(all)
    const { rerender } = render(<SegmentList transcriptId="t" />)
    await screen.findByRole('list')
    await settle()
    rerender(<SegmentList transcriptId="t" speakerFilter="spA" />)
    await settle()
    rerender(<SegmentList transcriptId="t" speakerFilter="spB" />)
    await settle()
    rerender(<SegmentList transcriptId="t" speakerFilter={null} />)
    await settle()

    const { rows } = layout()
    expect(rows.length).toBeGreaterThan(0)
    expect(rows.every((row) => row.text.trim() !== '')).toBe(true)
    expect(rows.every((row, i) => i === 0 || row.index === rows[i - 1]!.index + 1)).toBe(true)
    expect(rows.at(-1)!.top + rows.at(-1)!.height).toBeGreaterThanOrEqual(VIEWPORT)
  })

  it('el salto a un segmento lejano deja esa fila a la vista, medida y sin huecos', async () => {
    stubFetch(makeSegments(1500))
    const { rerender } = render(<SegmentList transcriptId="t" focus={null} />)
    await screen.findByRole('list')
    await settle()

    rerender(<SegmentList transcriptId="t" focus={{ segmentId: 's1201', nonce: 1 }} />)
    await settle()

    const { region, rows } = layout()
    const target = rows.find((row) => row.text === 'seg-1201-B')
    expect(target, 'la fila de destino está pintada').toBeDefined()
    const top = scrollTop(region)
    expect(target!.top).toBeGreaterThanOrEqual(top)
    expect(target!.top + target!.height).toBeLessThanOrEqual(top + VIEWPORT)
    expect(rows.every((row) => row.text.trim() !== '')).toBe(true)
    expect(rows.at(0)!.top).toBeLessThanOrEqual(top)
    expect(rows.at(-1)!.top + rows.at(-1)!.height).toBeGreaterThanOrEqual(top + VIEWPORT)
  })

  it('el salto lejano con el filtro puesto cae en la fila correcta del filtrado', async () => {
    stubFetch(makeSegments(1500))
    const { rerender } = render(<SegmentList transcriptId="t" speakerFilter="spB" focus={null} />)
    await screen.findByRole('list')
    await settle()

    rerender(
      <SegmentList transcriptId="t" speakerFilter="spB" focus={{ segmentId: 's1201', nonce: 1 }} />,
    )
    await settle()

    const { region, rows } = layout()
    const target = rows.find((row) => row.text === 'seg-1201-B')
    expect(target, 'la fila de destino está pintada').toBeDefined()
    expect(target!.index).toBe(600)
    const top = scrollTop(region)
    expect(target!.top).toBeGreaterThanOrEqual(top)
    expect(target!.top + target!.height).toBeLessThanOrEqual(top + VIEWPORT)
  })
})
