import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { SynthesisView } from '../api/synthesis'
import { useSynthesisEvents } from './useSynthesisEvents'

class FakeEventSource extends EventTarget {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSED = 2
  static instances: FakeEventSource[] = []

  readyState = FakeEventSource.OPEN
  readonly close = vi.fn(() => {
    this.readyState = FakeEventSource.CLOSED
  })

  constructor(readonly url: string) {
    super()
    FakeEventSource.instances.push(this)
  }
}

const ID = '11111111-1111-4111-8111-111111111111'

function view(overrides: Partial<SynthesisView> = {}): SynthesisView {
  return {
    id: ID,
    state: 'QUEUED',
    progress: 0,
    chunks_done: 0,
    chunks_total: 0,
    error_code: null,
    created_at: '2026-10-12T12:00:00+00:00',
    updated_at: '2026-10-12T12:00:00+00:00',
    started_at: null,
    provider_id: 'sherpa-onnx',
    model_id: 'piper-es',
    voice_id: '0',
    language: null,
    speed: 1,
    text_length: 10,
    text_preview: 'Hola',
    audio: null,
    ...overrides,
  }
}

const latest = (): FakeEventSource => {
  const source = FakeEventSource.instances.at(-1)
  if (!source) {
    throw new Error('no EventSource was opened')
  }
  return source
}

function emit(source: FakeEventSource, type: string, data: unknown) {
  act(() => {
    source.dispatchEvent(
      new MessageEvent(type, { data: typeof data === 'string' ? data : JSON.stringify(data) }),
    )
  })
}

beforeEach(() => {
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => undefined)))
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('useSynthesisEvents', () => {
  it('sigue el progreso hasta el fin y cierra el stream', () => {
    const { result } = renderHook(() => useSynthesisEvents(ID))

    expect(latest().url).toBe('/api/synthesis/' + ID + '/events')
    expect(result.current).toMatchObject({ job: null, ended: false, error: null })

    emit(latest(), 'job', view({ state: 'RUNNING', progress: 0.5, chunks_done: 1, chunks_total: 2 }))
    expect(result.current.job?.progress).toBe(0.5)

    emit(latest(), 'job', view({ state: 'COMPLETED', progress: 1 }))
    emit(latest(), 'end', {})
    expect(result.current.job?.state).toBe('COMPLETED')
    expect(result.current.ended).toBe(true)
    expect(latest().close).toHaveBeenCalledTimes(1)
  })

  it('muestra la instantánea HTTP mientras el stream no ha dicho nada', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(view({ state: 'RUNNING', progress: 0.25 })),
        } as unknown as Response),
      ),
    )
    const { result } = renderHook(() => useSynthesisEvents(ID))

    await waitFor(() => {
      expect(result.current.job?.progress).toBe(0.25)
    })
    emit(latest(), 'job', view({ state: 'RUNNING', progress: 0.75 }))
    expect(result.current.job?.progress).toBe(0.75)
  })

  it('sin id no abre nada', () => {
    const { result } = renderHook(() => useSynthesisEvents(null))
    expect(FakeEventSource.instances).toHaveLength(0)
    expect(result.current.job).toBeNull()
  })

  it('traduce el payload inválido y limpia el error con el siguiente snapshot', () => {
    const { result } = renderHook(() => useSynthesisEvents(ID))

    emit(latest(), 'job', '{no json')
    expect(result.current.error).toMatch(/inválido/)

    emit(latest(), 'job', view())
    expect(result.current.error).toBeNull()
  })

  it('conexión perdida: error y retry abre otro stream conservando el último estado', () => {
    const { result } = renderHook(() => useSynthesisEvents(ID))
    const first = latest()
    emit(first, 'job', view({ state: 'RUNNING', progress: 0.4 }))

    first.readyState = FakeEventSource.CLOSED
    act(() => {
      first.dispatchEvent(new Event('error'))
    })
    expect(result.current.error).toMatch(/conexión/)
    expect(result.current.job?.progress).toBe(0.4)

    act(() => {
      result.current.retry()
    })
    expect(FakeEventSource.instances).toHaveLength(2)
    expect(latest()).not.toBe(first)
    emit(latest(), 'job', view({ state: 'RUNNING', progress: 0.6 }))
    expect(result.current.error).toBeNull()
    expect(result.current.job?.progress).toBe(0.6)
  })

  it('cambia de id sin arrastrar el estado anterior y cierra al desmontar', () => {
    const other = '44444444-4444-4444-8444-444444444444'
    const initialProps: { id: string | null } = { id: ID }
    const { result, rerender, unmount } = renderHook(
      ({ id }: { id: string | null }) => useSynthesisEvents(id),
      { initialProps },
    )
    const first = latest()
    emit(first, 'job', view({ state: 'RUNNING' }))

    rerender({ id: other })
    expect(first.close).toHaveBeenCalledTimes(1)
    expect(latest().url).toBe('/api/synthesis/' + other + '/events')
    expect(result.current.job).toBeNull()

    emit(first, 'job', view({ state: 'COMPLETED' }))
    expect(result.current.job).toBeNull()

    unmount()
    expect(latest().close).toHaveBeenCalledTimes(1)
  })
})
