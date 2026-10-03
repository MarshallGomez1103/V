import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { PREVIEW_INTERVAL_MS, useJobPreview } from './useJobPreview'

const resp = (segments: unknown, status = 200) =>
  Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve({ segments }) })

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

const seg = (start: number, end: number, text: string) => ({ start_ms: start, end_ms: end, text })

describe('useJobPreview', () => {
  it('acumula segmentos sin duplicar y pide solo lo posterior a lo recibido', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => resp([seg(0, 1000, 'uno')]))
      .mockImplementationOnce(() => resp([seg(0, 1000, 'uno'), seg(1000, 2000, 'dos')]))
      .mockImplementation(() => resp([]))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useJobPreview('job-1', true))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.segments.map((s) => s.text)).toEqual(['uno'])

    await act(async () => {
      await vi.advanceTimersByTimeAsync(PREVIEW_INTERVAL_MS)
    })
    expect(result.current.segments.map((s) => s.text)).toEqual(['uno', 'dos'])
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/jobs/job-1/preview?after_ms=0')
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/jobs/job-1/preview?after_ms=0')
    await act(async () => {
      await vi.advanceTimersByTimeAsync(PREVIEW_INTERVAL_MS)
    })
    expect(fetchMock.mock.calls[2]?.[0]).toBe('/api/jobs/job-1/preview?after_ms=1000')
    expect(result.current.available).toBe(true)
  })

  it('no sondea si el trabajo no está transcribiendo', async () => {
    const fetchMock = vi.fn().mockImplementation(() => resp([]))
    vi.stubGlobal('fetch', fetchMock)
    renderHook(() => useJobPreview('job-1', false))
    renderHook(() => useJobPreview(null, true))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(PREVIEW_INTERVAL_MS * 3)
    })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('si el backend no ofrece vista previa lo marca y deja de insistir', async () => {
    const fetchMock = vi.fn().mockImplementation(() => resp({}, 404))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useJobPreview('job-1', true))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(PREVIEW_INTERVAL_MS * 5)
    })
    expect(result.current.available).toBe(false)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('un fallo puntual no rompe: reintenta más tarde', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => Promise.reject(new Error('red')))
      .mockImplementation(() => resp([seg(0, 500, 'hola')]))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useJobPreview('job-1', true))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(PREVIEW_INTERVAL_MS * 2 + 10)
    })
    expect(result.current.segments.map((s) => s.text)).toEqual(['hola'])
  })

  it('al cambiar de trabajo no muestra los segmentos del anterior', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => resp([seg(0, 500, 'viejo')])))
    const { result, rerender } = renderHook(({ id }) => useJobPreview(id, true), {
      initialProps: { id: 'a' },
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.segments).toHaveLength(1)
    rerender({ id: 'b' })
    expect(result.current.segments).toHaveLength(0)
  })
})
