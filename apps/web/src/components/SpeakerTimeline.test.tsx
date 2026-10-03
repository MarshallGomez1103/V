import { cleanup, fireEvent, render, screen, within, act } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { TranscriptSegment } from '../api/jobs'
import type { Speaker } from '../api/speakers'
import { createPlayhead } from '../lib/playhead'
import { SpeakerTimeline } from './SpeakerTimeline'

afterEach(cleanup)

function seg(id: string, start_ms: number, end_ms: number, speaker_id: string | null): TranscriptSegment {
  return {
    id,
    start_ms,
    end_ms,
    text: id,
    edited: false,
    revision: 0,
    speaker_id,
    quality: { flags: [], avg_logprob: null },
    words: [],
  }
}

const ANA: Speaker = { id: 'a', name: 'Ana', color: '#112233', segment_count: 2 }
const BETO: Speaker = { id: 'b', name: 'Beto', color: '#445566', segment_count: 1 }
const SEGMENTS = [
  seg('1', 0, 10_000, 'a'),
  seg('2', 10_000, 20_000, 'b'),
  seg('3', 60_000, 80_000, 'a'),
]

function track(name: RegExp) {
  return screen.getByRole('button', { name })
}

function mockRect(el: HTMLElement) {
  vi.spyOn(el, 'getBoundingClientRect').mockReturnValue({
    left: 100,
    width: 200,
    top: 0,
    bottom: 10,
    right: 300,
    height: 10,
    x: 100,
    y: 0,
    toJSON: () => ({}),
  })
}

describe('SpeakerTimeline', () => {
  it('dibuja una fila por hablante, con su color y sus bloques', () => {
    render(
      <SpeakerTimeline
        segments={SEGMENTS}
        speakers={[ANA, BETO]}
        durationMs={100_000}
        playhead={createPlayhead()}
        onSeek={() => undefined}
      />,
    )

    const ana = track(/^Ana: 2 bloques/)
    const beto = track(/^Beto: 1 bloques/)
    expect(ana.querySelectorAll('.voz-tl__block')).toHaveLength(2)
    expect(beto.querySelectorAll('.voz-tl__block')).toHaveLength(1)
    const block = ana.querySelector<HTMLElement>('.voz-tl__block')
    expect(block?.style.insetInlineStart).toBe('0%')
    expect(block?.style.inlineSize).toBe('10%')
    expect(block?.style.backgroundColor).toBe('rgb(17, 34, 51)')
    expect(screen.getByText('Una fila por hablante (2); un clic salta a ese momento.')).toBeDefined()
  })

  it('un clic salta al instante proporcional a la posición', () => {
    const onSeek = vi.fn()
    render(
      <SpeakerTimeline
        segments={SEGMENTS}
        speakers={[ANA, BETO]}
        durationMs={100_000}
        playhead={createPlayhead()}
        onSeek={onSeek}
      />,
    )
    const ana = track(/^Ana/)
    mockRect(ana)

    fireEvent.click(ana, { clientX: 200 }) // mitad del carril
    expect(onSeek).toHaveBeenLastCalledWith(50_000)
    fireEvent.click(ana, { clientX: 100 })
    expect(onSeek).toHaveBeenLastCalledWith(0)
    fireEvent.click(ana, { clientX: 999 }) // fuera: se acota al final
    expect(onSeek).toHaveBeenLastCalledWith(100_000)
  })

  it('las flechas saltan al bloque siguiente y anterior desde el cursor', () => {
    const onSeek = vi.fn()
    const playhead = createPlayhead()
    playhead.set(5_000)
    render(
      <SpeakerTimeline
        segments={SEGMENTS}
        speakers={[ANA, BETO]}
        durationMs={100_000}
        playhead={playhead}
        onSeek={onSeek}
      />,
    )
    const ana = track(/^Ana/)

    fireEvent.keyDown(ana, { key: 'ArrowRight' })
    expect(onSeek).toHaveBeenLastCalledWith(60_000)
    playhead.set(70_000)
    fireEvent.keyDown(ana, { key: 'ArrowLeft' }) // dentro de un bloque: va a su inicio
    expect(onSeek).toHaveBeenLastCalledWith(60_000)
    playhead.set(60_000)
    fireEvent.keyDown(ana, { key: 'ArrowLeft' })
    expect(onSeek).toHaveBeenLastCalledWith(0)
    onSeek.mockClear()
    fireEvent.keyDown(ana, { key: 'Enter' })
    expect(onSeek).not.toHaveBeenCalled()
  })

  it('el cursor sigue a la reproducción', () => {
    const playhead = createPlayhead()
    const { container } = render(
      <SpeakerTimeline
        segments={SEGMENTS}
        speakers={[ANA]}
        durationMs={100_000}
        playhead={playhead}
        onSeek={() => undefined}
      />,
    )
    expect(container.querySelector('.voz-tl__cursor')).toBeNull()

    act(() => {
      playhead.set(25_000)
    })
    expect(container.querySelector<HTMLElement>('.voz-tl__cursor')?.style.insetInlineStart).toBe('25%')
  })

  it('los segmentos sin hablante van a una fila aparte; sin hablantes, una sola fila «Voz»', () => {
    const { rerender } = render(
      <SpeakerTimeline
        segments={[...SEGMENTS, seg('4', 90_000, 95_000, null)]}
        speakers={[ANA, BETO]}
        durationMs={100_000}
        playhead={createPlayhead()}
        onSeek={() => undefined}
      />,
    )
    expect(track(/^Sin hablante: 1 bloques/)).toBeDefined()

    rerender(
      <SpeakerTimeline
        segments={[seg('1', 0, 10_000, null)]}
        speakers={[]}
        durationMs={100_000}
        playhead={createPlayhead()}
        onSeek={() => undefined}
      />,
    )
    expect(track(/^Voz: 1 bloques/)).toBeDefined()
  })

  it('mientras los hablantes se calculan lo avisa', () => {
    render(
      <SpeakerTimeline
        segments={[seg('1', 0, 10_000, null)]}
        speakers={[]}
        durationMs={100_000}
        playhead={createPlayhead()}
        onSeek={() => undefined}
        speakersPending
      />,
    )
    expect(screen.getByRole('status').textContent).toMatch(/los hablantes se están calculando/i)
  })

  it('sin duración conocida usa el último segmento; sin nada, explica que falta', () => {
    const { rerender } = render(
      <SpeakerTimeline
        segments={SEGMENTS}
        speakers={[ANA, BETO]}
        durationMs={null}
        playhead={createPlayhead()}
        onSeek={() => undefined}
      />,
    )
    expect(within(track(/^Ana/)).queryAllByTitle(/Ana/).length).toBeGreaterThan(0)

    rerender(
      <SpeakerTimeline
        segments={[]}
        speakers={[]}
        durationMs={null}
        playhead={createPlayhead()}
        onSeek={() => undefined}
      />,
    )
    expect(screen.getByText(/aún no hay duración/i)).toBeDefined()
  })

  it('1312 segmentos se reducen a pocos bloques y se pintan al instante', () => {
    const many = Array.from({ length: 1312 }, (_, i) =>
      seg('s' + i, i * 5000, i * 5000 + 4800, i % 3 === 0 ? 'a' : 'b'),
    )
    const started = performance.now()
    const { container } = render(
      <SpeakerTimeline
        segments={many}
        speakers={[ANA, BETO]}
        durationMs={1312 * 5000}
        playhead={createPlayhead()}
        onSeek={() => undefined}
      />,
    )
    expect(container.querySelectorAll('.voz-tl__block').length).toBeGreaterThan(100)
    expect(container.querySelectorAll('.voz-tl__block').length).toBeLessThan(1400)
    expect(performance.now() - started).toBeLessThan(2000)
  })
})
