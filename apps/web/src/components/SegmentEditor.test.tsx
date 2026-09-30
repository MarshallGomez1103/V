import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AUTOSAVE_DEBOUNCE_MS, SegmentDraftStore } from '../hooks/useSegmentDrafts'
import { SegmentEditor } from './SegmentEditor'

const SEG = { id: 's1', text: 'original', revision: 1 }

function respond(status: number, body: unknown) {
  return {
    ok: status < 300,
    status,
    json: () => Promise.resolve(body),
  }
}

function editor() {
  return screen.getByRole('textbox', { name: /Texto del segmento/ })
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('SegmentEditor', () => {
  it('muestra un textarea accesible con el texto del segmento', () => {
    render(<SegmentEditor segment={SEG} drafts={new SegmentDraftStore()} />)

    expect((editor() as HTMLTextAreaElement).value).toBe('original')
    expect(editor().tagName).toBe('TEXTAREA')
    expect(screen.queryByText('Sin guardar')).toBeNull()
  })

  it('autoguarda tras el debounce y muestra el estado del segmento', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(respond(200, { id: 's1', text: 'hola', revision: 2 }))
    vi.stubGlobal('fetch', fetchMock)
    render(<SegmentEditor segment={SEG} drafts={new SegmentDraftStore()} />)

    fireEvent.change(editor(), { target: { value: 'hola' } })
    expect(screen.getByText('Sin guardar')).toBeTruthy()
    expect(fetchMock).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Guardado')).toBeTruthy()
  })

  it('guarda de inmediato al perder el foco', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(respond(200, { id: 's1', text: 'hola', revision: 2 }))
    vi.stubGlobal('fetch', fetchMock)
    render(<SegmentEditor segment={SEG} drafts={new SegmentDraftStore()} />)

    fireEvent.change(editor(), { target: { value: 'hola' } })
    fireEvent.blur(editor())
    await vi.advanceTimersByTimeAsync(0)

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('Escape revierte al último texto guardado', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<SegmentEditor segment={SEG} drafts={new SegmentDraftStore()} />)

    fireEvent.change(editor(), { target: { value: 'cambio' } })
    fireEvent.keyDown(editor(), { key: 'Escape' })
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS * 2)

    expect((editor() as HTMLTextAreaElement).value).toBe('original')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('desmontar y volver a montar conserva el borrador', () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => undefined)))
    const drafts = new SegmentDraftStore()
    const first = render(<SegmentEditor segment={SEG} drafts={drafts} />)

    fireEvent.change(editor(), { target: { value: 'borrador' } })
    first.unmount()
    render(<SegmentEditor segment={SEG} drafts={drafts} />)

    expect((editor() as HTMLTextAreaElement).value).toBe('borrador')
    expect(screen.getByText('Sin guardar')).toBeTruthy()
  })

  it('error de red: conserva el texto y ofrece Reintentar', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockResolvedValueOnce(respond(200, { id: 's1', text: 'hola', revision: 2 }))
    vi.stubGlobal('fetch', fetchMock)
    render(<SegmentEditor segment={SEG} drafts={new SegmentDraftStore()} />)

    fireEvent.change(editor(), { target: { value: 'hola' } })
    fireEvent.blur(editor())
    await vi.advanceTimersByTimeAsync(0)

    expect(screen.getByText('Error al guardar')).toBeTruthy()
    expect((editor() as HTMLTextAreaElement).value).toBe('hola')

    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await vi.advanceTimersByTimeAsync(0)
    expect(screen.getByText('Guardado')).toBeTruthy()
  })

  it('conflicto: muestra la versión del servidor y permite elegir', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        respond(409, {
          detail: {
            code: 'segment_revision_conflict',
            message: 'x',
            current: { id: 's1', text: 'versión servidor', revision: 3 },
          },
        }),
      )
      .mockResolvedValueOnce(respond(200, { id: 's1', text: 'mía', revision: 4 }))
    vi.stubGlobal('fetch', fetchMock)
    render(<SegmentEditor segment={SEG} drafts={new SegmentDraftStore()} />)

    fireEvent.change(editor(), { target: { value: 'mía' } })
    fireEvent.blur(editor())
    await vi.advanceTimersByTimeAsync(0)

    expect(screen.getByRole('alert').textContent).toContain('versión servidor')
    expect((editor() as HTMLTextAreaElement).value).toBe('mía')

    fireEvent.click(screen.getByRole('button', { name: 'Usar mi versión' }))
    await vi.advanceTimersByTimeAsync(0)

    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/segments/s1',
      expect.objectContaining({
        body: JSON.stringify({ text: 'mía', revision: 3 }),
      }),
    )
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByText('Guardado')).toBeTruthy()
  })

  it('conflicto: Descartar toma el texto del servidor', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        respond(409, {
          detail: {
            code: 'segment_revision_conflict',
            message: 'x',
            current: { id: 's1', text: 'versión servidor', revision: 3 },
          },
        }),
      ),
    )
    render(<SegmentEditor segment={SEG} drafts={new SegmentDraftStore()} />)

    fireEvent.change(editor(), { target: { value: 'mía' } })
    fireEvent.blur(editor())
    await vi.advanceTimersByTimeAsync(0)
    fireEvent.click(screen.getByRole('button', { name: 'Descartar' }))

    expect((editor() as HTMLTextAreaElement).value).toBe('versión servidor')
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
