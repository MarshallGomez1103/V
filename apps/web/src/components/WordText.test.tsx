import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { TranscriptSegment } from '../api/jobs'
import { createPlayhead } from '../lib/playhead'
import { WordText } from './WordText'

afterEach(cleanup)

function segment(overrides: Partial<TranscriptSegment> = {}): TranscriptSegment {
  return {
    id: 's1',
    start_ms: 1000,
    end_ms: 2000,
    text: 'hola mundo feliz',
    edited: false,
    revision: 0,
    speaker_id: null,
    words: [
      { start_ms: 1000, end_ms: 1300, text: 'hola', speaker_id: null },
      { start_ms: 1300, end_ms: 1600, text: 'mundo', speaker_id: null },
      { start_ms: 1600, end_ms: 2000, text: 'feliz', speaker_id: null },
    ],
    ...overrides,
  }
}

describe('WordText', () => {
  it('hace seek al inicio de la palabra clicada', () => {
    const onSeek = vi.fn()
    render(<WordText segment={segment()} onSeek={onSeek} />)

    fireEvent.click(screen.getByText('mundo'))

    expect(onSeek).toHaveBeenCalledExactlyOnceWith(1300)
  })

  it('expone palabras como botones con un solo tab-stop y flechas', () => {
    const onSeek = vi.fn()
    render(<WordText segment={segment()} onSeek={onSeek} />)

    const buttons = screen.getAllByRole('button')
    expect(buttons.map((b) => b.tabIndex)).toEqual([0, -1, -1])

    buttons[0]?.focus()
    fireEvent.keyDown(buttons[0] as HTMLElement, { key: 'ArrowRight' })
    expect(document.activeElement).toBe(buttons[1])
    fireEvent.keyDown(buttons[1] as HTMLElement, { key: 'Enter' })
    expect(onSeek).toHaveBeenCalledWith(1300)
    fireEvent.keyDown(buttons[1] as HTMLElement, { key: 'ArrowLeft' })
    expect(document.activeElement).toBe(buttons[0])
  })

  it('sin onSeek no hay botones ni manejadores', () => {
    render(<WordText segment={segment()} />)

    expect(screen.queryAllByRole('button')).toHaveLength(0)
    expect(screen.getByText('mundo')).toBeTruthy()
  })

  it('marca la palabra actual con aria-current según currentMs', () => {
    const { rerender } = render(<WordText segment={segment()} currentMs={1400} />)
    expect(screen.getByText('mundo').getAttribute('aria-current')).toBe('true')
    expect(screen.getByText('hola').getAttribute('aria-current')).toBeNull()

    // Fuera del segmento no hay palabra actual, aunque sea posterior a todas.
    rerender(<WordText segment={segment()} currentMs={2500} />)
    expect(document.querySelector('[aria-current]')).toBeNull()
  })

  it('sigue el playhead sin re-renderizar por props', () => {
    const playhead = createPlayhead()
    render(<WordText segment={segment()} playhead={playhead} />)
    expect(document.querySelector('[aria-current]')).toBeNull()

    act(() => {
      playhead.set(1700)
    })
    expect(screen.getByText('feliz').getAttribute('aria-current')).toBe('true')

    act(() => {
      playhead.set(500)
    })
    expect(document.querySelector('[aria-current]')).toBeNull()
  })

  it('resalta la búsqueda con <mark>, también entre palabras', () => {
    const { container } = render(<WordText segment={segment()} query="Mundo fel" />)

    expect(
      Array.from(container.querySelectorAll('mark')).map((m) => m.textContent),
    ).toEqual(['mundo', 'fel'])
    expect(container.textContent).toBe('hola mundo feliz')
  })

  it('sin palabras (o editado) muestra el texto plano con búsqueda', () => {
    const { container } = render(
      <WordText segment={segment({ words: [] })} query="mundo" onSeek={vi.fn()} />,
    )

    expect(screen.queryAllByRole('button')).toHaveLength(0)
    expect(container.querySelector('mark')?.textContent).toBe('mundo')
    expect(container.textContent).toBe('hola mundo feliz')
  })
})
