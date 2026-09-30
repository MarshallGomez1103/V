import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { TaskView } from '../api/models'
import { POLL_INTERVAL_MS, useModelTasks } from './useModelTasks'

function task(overrides: Partial<TaskView> = {}): TaskView {
  return {
    id: 't1',
    model_id: 'turbo',
    method: 'download',
    origin: null,
    state: 'running',
    done_bytes: 10,
    total_bytes: 100,
    error_code: null,
    created_at: '2026-09-30T10:00:00Z',
    updated_at: '2026-09-30T10:00:00Z',
    ...overrides,
  }
}

function listResponse(...tasks: TaskView[]): Response {
  return {
    ok: true,
    status: 200,
    json: () => Promise.resolve({ tasks }),
  } as unknown as Response
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

function stubFetch(...responses: Response[]) {
  const fetchMock = vi.fn<typeof fetch>()
  for (const response of responses) {
    fetchMock.mockResolvedValueOnce(response)
  }
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('useModelTasks', () => {
  it('no sondea mientras no haya tareas activas', async () => {
    const fetchMock = stubFetch(listResponse(task({ state: 'completed' })))

    const { result } = renderHook(() => useModelTasks())
    await act(() => vi.advanceTimersByTimeAsync(0))
    expect(result.current.tasks).toHaveLength(1)

    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 5))
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('sondea cada segundo mientras haya una activa y avisa una vez al completarse', async () => {
    const onCompleted = vi.fn()
    const fetchMock = stubFetch(
      listResponse(task({ done_bytes: 10 })),
      listResponse(task({ done_bytes: 60 })),
      listResponse(task({ state: 'completed', done_bytes: 100 })),
    )

    const { result } = renderHook(() => useModelTasks(onCompleted))
    await act(() => vi.advanceTimersByTimeAsync(0))
    expect(result.current.tasks[0]?.done_bytes).toBe(10)
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS))
    expect(result.current.tasks[0]?.done_bytes).toBe(60)
    expect(onCompleted).not.toHaveBeenCalled()

    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS))
    expect(result.current.tasks[0]?.state).toBe('completed')
    expect(onCompleted).toHaveBeenCalledTimes(1)
    expect(onCompleted).toHaveBeenCalledWith(
      expect.objectContaining({ id: 't1', state: 'completed' }),
    )

    // Terminada: se detiene el sondeo.
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3))
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('no avisa de tareas que ya estaban completadas al cargar', async () => {
    const onCompleted = vi.fn()
    stubFetch(listResponse(task({ state: 'completed' })))

    renderHook(() => useModelTasks(onCompleted))
    await act(() => vi.advanceTimersByTimeAsync(0))

    expect(onCompleted).not.toHaveBeenCalled()
  })

  it('track empieza a sondear una tarea nueva', async () => {
    const created = task({ id: 't9', state: 'queued', done_bytes: 0 })
    const fetchMock = stubFetch(
      listResponse(),
      listResponse(created),
      listResponse({ ...created, state: 'running', done_bytes: 50 }),
    )

    const { result } = renderHook(() => useModelTasks())
    await act(() => vi.advanceTimersByTimeAsync(0))
    expect(result.current.tasks).toHaveLength(0)

    act(() => {
      result.current.track(created)
    })
    expect(result.current.tasks[0]?.id).toBe('t9')
    await act(() => vi.advanceTimersByTimeAsync(0))
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS))

    expect(result.current.tasks[0]?.done_bytes).toBe(50)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('reporta el error de sondeo y sigue reintentando', async () => {
    const fetchMock = vi.fn<typeof fetch>()
    fetchMock
      .mockResolvedValueOnce(listResponse(task()))
      .mockRejectedValueOnce(new Error('sin red'))
      .mockResolvedValueOnce(listResponse(task({ done_bytes: 80 })))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useModelTasks())
    await act(() => vi.advanceTimersByTimeAsync(0))
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS))
    expect(result.current.error).toBe('sin red')

    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS))
    expect(result.current.error).toBeNull()
    expect(result.current.tasks[0]?.done_bytes).toBe(80)
  })

  it('aborta la consulta en vuelo y deja de sondear al desmontar', () => {
    const fetchMock = vi.fn<typeof fetch>()
    fetchMock.mockReturnValue(new Promise<Response>(() => undefined))
    vi.stubGlobal('fetch', fetchMock)

    const { unmount } = renderHook(() => useModelTasks())
    const signal = fetchMock.mock.calls[0]?.[1]?.signal
    expect(signal?.aborted).toBe(false)

    unmount()

    expect(signal?.aborted).toBe(true)
  })
})
