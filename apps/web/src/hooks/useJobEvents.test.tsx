import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { JobView } from '../api/jobEvents'
import { useJobEvents } from './useJobEvents'

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

const JOB_ID = '11111111-1111-4111-8111-111111111111'

function view(overrides: Partial<JobView> = {}): JobView {
  return {
    id: JOB_ID,
    project_id: '22222222-2222-4222-8222-222222222222',
    media_asset_id: '33333333-3333-4333-8333-333333333333',
    state: 'QUEUED',
    progress: 0,
    error_code: null,
    transcript_id: null,
    created_at: '2026-09-21T12:00:00+00:00',
    updated_at: '2026-09-21T12:00:00+00:00',
    ...overrides,
  }
}

function latest(): FakeEventSource {
  const source = FakeEventSource.instances.at(-1)
  if (!source) {
    throw new Error('no EventSource was opened')
  }
  return source
}

function emit(source: FakeEventSource, type: string, data: unknown) {
  act(() => {
    source.dispatchEvent(
      new MessageEvent(type, {
        data: typeof data === 'string' ? data : JSON.stringify(data),
      }),
    )
  })
}

beforeEach(() => {
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('useJobEvents', () => {
  it('abre el stream del job y refleja cada snapshot hasta el fin', () => {
    const { result } = renderHook(() => useJobEvents(JOB_ID))

    expect(latest().url).toBe('/api/jobs/' + JOB_ID + '/events')
    expect(result.current).toEqual({ job: null, ended: false, error: null })

    emit(latest(), 'job', view())
    expect(result.current.job?.state).toBe('QUEUED')

    emit(latest(), 'job', view({ state: 'TRANSCRIBING', progress: 0.5 }))
    expect(result.current.job?.progress).toBe(0.5)
    expect(result.current.ended).toBe(false)

    emit(latest(), 'job', view({ state: 'COMPLETED', progress: 1 }))
    emit(latest(), 'end', {})
    expect(result.current.job?.state).toBe('COMPLETED')
    expect(result.current.ended).toBe(true)
    expect(latest().close).toHaveBeenCalledTimes(1)
  })

  it('no abre ningún stream sin id', () => {
    const { result } = renderHook(() => useJobEvents(null))
    expect(FakeEventSource.instances).toHaveLength(0)
    expect(result.current).toEqual({ job: null, ended: false, error: null })
  })

  it('reporta payloads inválidos y limpia el error con el siguiente snapshot', () => {
    const { result } = renderHook(() => useJobEvents(JOB_ID))

    emit(latest(), 'job', '{not json')
    expect(result.current.error).toMatch(/inválido/)
    expect(result.current.job).toBeNull()

    emit(latest(), 'job', { id: JOB_ID })
    expect(result.current.error).toMatch(/inválido/)

    emit(latest(), 'job', view())
    expect(result.current.error).toBeNull()
    expect(result.current.job?.id).toBe(JOB_ID)
  })

  it('reporta la conexión perdida solo cuando el navegador la cierra', () => {
    const { result } = renderHook(() => useJobEvents(JOB_ID))
    const source = latest()

    act(() => {
      source.dispatchEvent(new Event('error'))
    })
    expect(result.current.error).toBeNull()

    source.readyState = FakeEventSource.CLOSED
    act(() => {
      source.dispatchEvent(new Event('error'))
    })
    expect(result.current.error).toMatch(/conexión/)
  })

  it('cierra el stream anterior y reinicia el estado al cambiar de id', () => {
    const otherId = '44444444-4444-4444-8444-444444444444'
    const initialProps: { jobId: string | null } = { jobId: JOB_ID }
    const { result, rerender } = renderHook(
      ({ jobId }: { jobId: string | null }) => useJobEvents(jobId),
      { initialProps },
    )
    const first = latest()
    emit(first, 'job', view({ state: 'TRANSCRIBING' }))
    expect(result.current.job?.state).toBe('TRANSCRIBING')

    rerender({ jobId: otherId })
    expect(first.close).toHaveBeenCalledTimes(1)
    expect(FakeEventSource.instances).toHaveLength(2)
    expect(latest().url).toBe('/api/jobs/' + otherId + '/events')
    expect(result.current).toEqual({ job: null, ended: false, error: null })

    emit(first, 'job', view({ state: 'COMPLETED' }))
    expect(result.current.job).toBeNull()

    rerender({ jobId: null })
    expect(latest().close).toHaveBeenCalledTimes(1)
    expect(result.current).toEqual({ job: null, ended: false, error: null })
  })

  it('cierra el stream al desmontar', () => {
    const { unmount } = renderHook(() => useJobEvents(JOB_ID))
    unmount()
    expect(latest().close).toHaveBeenCalledTimes(1)
  })
})
