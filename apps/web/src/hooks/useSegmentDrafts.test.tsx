import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  AUTOSAVE_DEBOUNCE_MS,
  SegmentDraftStore,
  useSegmentDrafts,
} from './useSegmentDrafts'

const SEG = { id: 's1', text: 'original', revision: 1 }

interface Call {
  body: { text: string; revision: number }
  resolve: (status: number, body: unknown) => void
  reject: (error: unknown) => void
}

/** fetch controlable: cada PUT queda pendiente hasta que el test lo resuelva. */
function stubFetch() {
  const calls: Call[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((_url: string, init: RequestInit) => {
      return new Promise((resolve, reject) => {
        calls.push({
          body: JSON.parse(init.body as string) as Call['body'],
          resolve: (status, body) => {
            resolve({
              ok: status < 300,
              status,
              json: () => Promise.resolve(body),
            })
          },
          reject,
        })
      })
    }),
  )
  return calls
}

function item(text: string, revision: number) {
  return {
    id: 's1',
    start_ms: 0,
    end_ms: 1,
    text,
    edited: true,
    revision,
    speaker_id: null,
    words: [],
  }
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('SegmentDraftStore', () => {
  it('guarda con debounce y actualiza la revisión conocida', async () => {
    const calls = stubFetch()
    const store = new SegmentDraftStore()

    store.edit(SEG, 'a')
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS - 1)
    store.edit(SEG, 'ab')
    expect(store.getDraft('s1')?.status).toBe('dirty')
    expect(store.getStatus()).toBe('dirty')

    await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS - 1)
    expect(calls).toHaveLength(0)
    await vi.advanceTimersByTimeAsync(1)
    expect(calls).toHaveLength(1)
    expect(calls[0]?.body).toEqual({ text: 'ab', revision: 1 })
    expect(store.getStatus()).toBe('saving')

    calls[0]?.resolve(200, item('ab', 2))
    await vi.advanceTimersByTimeAsync(0)

    expect(store.getDraft('s1')).toMatchObject({
      status: 'saved',
      text: 'ab',
      base: { revision: 2, text: 'ab' },
    })
    expect(store.getStatus()).toBe('saved')
    expect(store.hasPending()).toBe(false)
  })

  it('flush guarda de inmediato sin esperar el debounce', async () => {
    const calls = stubFetch()
    const store = new SegmentDraftStore()

    store.edit(SEG, 'nuevo')
    store.flush('s1')
    await vi.advanceTimersByTimeAsync(0)

    expect(calls).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS * 2)
    expect(calls).toHaveLength(1)
  })

  it('serializa: con un PUT en vuelo, dos ediciones rápidas envían solo el último texto después', async () => {
    const calls = stubFetch()
    const store = new SegmentDraftStore()

    store.edit(SEG, 'uno')
    store.flush('s1')
    await vi.advanceTimersByTimeAsync(0)
    expect(calls).toHaveLength(1)

    store.edit(SEG, 'dos')
    store.edit(SEG, 'tres')
    store.flush('s1')
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS * 2)
    // Sigue habiendo un único PUT en vuelo.
    expect(calls).toHaveLength(1)

    calls[0]?.resolve(200, item('uno', 2))
    await vi.advanceTimersByTimeAsync(0)

    expect(calls).toHaveLength(2)
    expect(calls[1]?.body).toEqual({ text: 'tres', revision: 2 })

    calls[1]?.resolve(200, item('tres', 3))
    await vi.advanceTimersByTimeAsync(0)
    expect(store.getDraft('s1')).toMatchObject({ status: 'saved', text: 'tres' })
    expect(calls).toHaveLength(2)
  })

  it('409 conserva el borrador y expone la versión del servidor', async () => {
    const calls = stubFetch()
    const store = new SegmentDraftStore()

    store.edit(SEG, 'mío')
    store.flush('s1')
    await vi.advanceTimersByTimeAsync(0)
    calls[0]?.resolve(409, {
      detail: {
        code: 'segment_revision_conflict',
        message: 'x',
        current: { id: 's1', text: 'servidor', revision: 4 },
      },
    })
    await vi.advanceTimersByTimeAsync(0)

    expect(store.getDraft('s1')).toMatchObject({
      status: 'conflict',
      text: 'mío',
      conflict: { text: 'servidor', revision: 4 },
    })
    expect(store.getStatus()).toBe('conflict')
    expect(store.hasPending()).toBe(true)

    // Editar durante el conflicto no dispara autosave ni pierde el texto.
    store.edit(SEG, 'mío 2')
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS * 2)
    expect(calls).toHaveLength(1)
    expect(store.getDraft('s1')?.text).toBe('mío 2')
  })

  it('"Usar mi versión" reintenta con la revisión nueva', async () => {
    const calls = stubFetch()
    const store = new SegmentDraftStore()
    store.edit(SEG, 'mío')
    store.flush('s1')
    await vi.advanceTimersByTimeAsync(0)
    calls[0]?.resolve(409, {
      detail: {
        code: 'segment_revision_conflict',
        message: 'x',
        current: { id: 's1', text: 'servidor', revision: 4 },
      },
    })
    await vi.advanceTimersByTimeAsync(0)

    store.keepMine('s1')
    await vi.advanceTimersByTimeAsync(0)

    expect(calls).toHaveLength(2)
    expect(calls[1]?.body).toEqual({ text: 'mío', revision: 4 })
    calls[1]?.resolve(200, item('mío', 5))
    await vi.advanceTimersByTimeAsync(0)
    expect(store.getDraft('s1')).toMatchObject({
      status: 'saved',
      text: 'mío',
      base: { revision: 5 },
    })
  })

  it('"Descartar" toma la versión del servidor', async () => {
    const calls = stubFetch()
    const store = new SegmentDraftStore()
    store.edit(SEG, 'mío')
    store.flush('s1')
    await vi.advanceTimersByTimeAsync(0)
    calls[0]?.resolve(409, {
      detail: {
        code: 'segment_revision_conflict',
        message: 'x',
        current: { id: 's1', text: 'servidor', revision: 4 },
      },
    })
    await vi.advanceTimersByTimeAsync(0)

    store.discard('s1')

    expect(store.getDraft('s1')).toMatchObject({
      status: 'saved',
      text: 'servidor',
      base: { revision: 4, text: 'servidor' },
    })
    expect(calls).toHaveLength(1)
    expect(store.getStatus()).toBe('saved')
  })

  it('un error de red conserva el borrador y permite reintentar', async () => {
    const calls = stubFetch()
    const store = new SegmentDraftStore()

    store.edit(SEG, 'texto')
    store.flush('s1')
    await vi.advanceTimersByTimeAsync(0)
    calls[0]?.reject(new TypeError('offline'))
    await vi.advanceTimersByTimeAsync(0)

    expect(store.getDraft('s1')).toMatchObject({
      status: 'error',
      text: 'texto',
      base: { revision: 1 },
    })
    expect(store.getStatus()).toBe('error')

    store.retry('s1')
    await vi.advanceTimersByTimeAsync(0)
    expect(calls).toHaveLength(2)
    expect(calls[1]?.body).toEqual({ text: 'texto', revision: 1 })
    calls[1]?.resolve(200, item('texto', 2))
    await vi.advanceTimersByTimeAsync(0)
    expect(store.getStatus()).toBe('saved')
  })

  it('revert vuelve al último texto guardado y cancela el autosave', async () => {
    const calls = stubFetch()
    const store = new SegmentDraftStore()

    store.edit(SEG, 'cambio')
    store.revert('s1')
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS * 2)

    expect(store.getDraft('s1')).toMatchObject({ status: 'saved', text: 'original' })
    expect(calls).toHaveLength(0)
  })

  it('el estado agregado prioriza lo que exige acción', async () => {
    const calls = stubFetch()
    const store = new SegmentDraftStore()

    store.edit(SEG, 'a')
    store.edit({ id: 's2', text: 'x', revision: 1 }, 'y')
    store.flush('s1')
    await vi.advanceTimersByTimeAsync(0)
    expect(store.getStatus()).toBe('saving')

    calls[0]?.reject(new TypeError('offline'))
    await vi.advanceTimersByTimeAsync(0)
    expect(store.getStatus()).toBe('error')
  })

  it('notifica a los suscriptores', () => {
    stubFetch()
    const store = new SegmentDraftStore()
    const listener = vi.fn()
    const unsubscribe = store.subscribe(listener)

    store.edit(SEG, 'a')
    expect(listener).toHaveBeenCalledTimes(1)

    unsubscribe()
    store.edit(SEG, 'ab')
    expect(listener).toHaveBeenCalledTimes(1)
  })
})

describe('useSegmentDrafts', () => {
  it('devuelve el mismo almacén entre renders', () => {
    const { result, rerender } = renderHook(() => useSegmentDrafts())
    const first = result.current
    rerender()
    expect(result.current).toBe(first)
  })

  it('avisa con beforeunload solo mientras hay borradores pendientes', async () => {
    const calls = stubFetch()
    const { result } = renderHook(() => useSegmentDrafts())

    const fire = () => {
      const event = new Event('beforeunload', { cancelable: true })
      window.dispatchEvent(event)
      return event.defaultPrevented
    }

    expect(fire()).toBe(false)

    act(() => {
      result.current.edit(SEG, 'cambio')
    })
    expect(fire()).toBe(true)

    act(() => {
      result.current.flush('s1')
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(fire()).toBe(true) // sigue en vuelo

    await act(async () => {
      calls[0]?.resolve(200, item('cambio', 2))
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(fire()).toBe(false)
  })
})
