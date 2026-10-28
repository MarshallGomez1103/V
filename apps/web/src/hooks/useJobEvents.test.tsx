import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { JobView } from '../api/jobEvents'
import { setLang } from '../i18n/i18n'
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

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
  // Por defecto la instantánea HTTP queda pendiente: solo habla el stream.
  fetchMock = vi.fn(() => new Promise<Response>(() => undefined))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  setLang('es')
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

  it('si la instantánea HTTP falla y el stream sigue abierto, el error se ve', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const { result } = renderHook(() => useJobEvents(JOB_ID))

    await waitFor(() => {
      expect(result.current.error).toMatch(/No se pudo conectar/)
    })
    expect(result.current.job).toBeNull()
  })

  it('un trabajo inexistente en la instantánea se explica con su mensaje', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: { code: 'job_not_found', message: 'x' } }), {
        status: 404,
      }),
    )
    const { result } = renderHook(() => useJobEvents(JOB_ID))

    await waitFor(() => {
      expect(result.current.error).toBe('La transcripción ya no existe.')
    })
  })

  it('el siguiente snapshot del stream limpia el error de la instantánea', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const { result } = renderHook(() => useJobEvents(JOB_ID))
    await waitFor(() => {
      expect(result.current.error).not.toBeNull()
    })

    emit(latest(), 'job', view())
    expect(result.current.error).toBeNull()
    expect(result.current.job?.id).toBe(JOB_ID)
  })

  it('una instantánea fallida no tapa un trabajo que el stream ya entregó', async () => {
    let fail: (reason: unknown) => void = () => undefined
    fetchMock.mockReturnValue(
      new Promise<Response>((_resolve, reject) => {
        fail = reject
      }),
    )
    const { result } = renderHook(() => useJobEvents(JOB_ID))
    emit(latest(), 'job', view({ state: 'TRANSCRIBING' }))

    await act(async () => {
      fail(new TypeError('Failed to fetch'))
      await Promise.resolve()
    })
    expect(result.current.error).toBeNull()
    expect(result.current.job?.state).toBe('TRANSCRIBING')
  })

  it('cambiar el intento vuelve a pedir la instantánea y reabre el stream', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    const { result, rerender } = renderHook(
      ({ attempt }: { attempt: number }) => useJobEvents(JOB_ID, attempt),
      { initialProps: { attempt: 0 } },
    )
    await waitFor(() => {
      expect(result.current.error).not.toBeNull()
    })
    const first = latest()

    fetchMock.mockResolvedValue(new Response(JSON.stringify(view({ state: 'COMPLETED' }))))
    rerender({ attempt: 1 })

    expect(first.close).toHaveBeenCalledTimes(1)
    expect(FakeEventSource.instances).toHaveLength(2)
    await waitFor(() => {
      expect(result.current.job?.state).toBe('COMPLETED')
    })
    expect(result.current.error).toBeNull()
  })

  it('los errores del stream salen en el idioma activo', () => {
    setLang('en')
    const { result } = renderHook(() => useJobEvents(JOB_ID))

    emit(latest(), 'job', '{not json')
    expect(result.current.error).toBe('The server sent an invalid job state.')

    latest().readyState = FakeEventSource.CLOSED
    act(() => {
      latest().dispatchEvent(new Event('error'))
    })
    expect(result.current.error).toBe('The connection to the job events was lost.')
  })

  it('al reintentar limpia el error enseguida, para que se vea que está cargando', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    const { result, rerender } = renderHook(
      ({ attempt }: { attempt: number }) => useJobEvents(JOB_ID, attempt),
      { initialProps: { attempt: 0 } },
    )
    await waitFor(() => {
      expect(result.current.error).not.toBeNull()
    })

    fetchMock.mockReturnValue(new Promise<Response>(() => undefined))
    rerender({ attempt: 1 })
    expect(result.current.error).toBeNull()
  })

  it('si la instantánea dice que no existe, la pérdida del stream no tapa ese mensaje', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: { code: 'job_not_found', message: 'x' } }), {
        status: 404,
      }),
    )
    const { result } = renderHook(() => useJobEvents(JOB_ID))
    await waitFor(() => {
      expect(result.current.error).toBe('La transcripción ya no existe.')
    })

    latest().readyState = FakeEventSource.CLOSED
    act(() => {
      latest().dispatchEvent(new Event('error'))
    })
    expect(result.current.error).toBe('La transcripción ya no existe.')
    expect(result.current.notFound).toBe(true)
  })
})
