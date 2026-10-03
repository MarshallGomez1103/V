import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { DOWN_INTERVAL_MS, UP_INTERVAL_MS, useServerStatus } from './useServerStatus'

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('useServerStatus', () => {
  it('no consulta nada al montar: espera al primer intervalo', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => useServerStatus(true))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(UP_INTERVAL_MS - 1)
    })
    expect(fetchMock).not.toHaveBeenCalled()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2)
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('avisa tras dos fallos seguidos y se recupera solo', async () => {
    let up = false
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() =>
        up ? Promise.resolve({ ok: true }) : Promise.reject(new TypeError('caído')),
      ),
    )
    const { result } = renderHook(() => useServerStatus(true))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(UP_INTERVAL_MS + 1)
    })
    expect(result.current.down).toBe(false) // un fallo suelto no es una caída

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DOWN_INTERVAL_MS + 1)
    })
    expect(result.current.down).toBe(true)

    up = true
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DOWN_INTERVAL_MS + 1)
    })
    expect(result.current.down).toBe(false)
  })

  it('una respuesta con error HTTP cuenta como fallo', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))
    const { result } = renderHook(() => useServerStatus(true))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(UP_INTERVAL_MS + DOWN_INTERVAL_MS + 10)
    })
    expect(result.current.down).toBe(true)
  })

  it('check() vuelve a comprobar de inmediato', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('caído'))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useServerStatus(true))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(UP_INTERVAL_MS + DOWN_INTERVAL_MS + 10)
    })
    const before = fetchMock.mock.calls.length
    act(() => {
      result.current.check()
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(fetchMock.mock.calls.length).toBeGreaterThan(before)
  })

  it('apagado no consulta', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => useServerStatus(false))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(UP_INTERVAL_MS * 3)
    })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
