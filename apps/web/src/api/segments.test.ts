import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  SegmentApiError,
  SegmentConflictError,
  updateSegment,
} from './segments'

afterEach(() => {
  vi.unstubAllGlobals()
})

function stubFetch(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('updateSegment', () => {
  it('hace PUT con texto y revisión y devuelve el segmento guardado', async () => {
    const fetchMock = stubFetch({
      id: 'a/b',
      start_ms: 0,
      end_ms: 10,
      text: 'nuevo',
      edited: true,
      revision: 3,
      speaker_id: null,
    })

    await expect(
      updateSegment('a/b', { text: 'nuevo', revision: 2 }),
    ).resolves.toEqual({ id: 'a/b', text: 'nuevo', revision: 3 })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/segments/a%2Fb',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ text: 'nuevo', revision: 2 }),
      }),
    )
  })

  it('409 lanza SegmentConflictError con el segmento actual', async () => {
    stubFetch(
      {
        detail: {
          code: 'segment_revision_conflict',
          message: 'x',
          current: { id: 's1', text: 'del servidor', revision: 5 },
        },
      },
      409,
    )

    const error = await updateSegment('s1', { text: 'mío', revision: 4 }).catch(
      (e: unknown) => e,
    )

    expect(error).toBeInstanceOf(SegmentConflictError)
    expect((error as SegmentConflictError).current).toEqual({
      id: 's1',
      text: 'del servidor',
      revision: 5,
    })
  })

  it.each([
    [404, 'segment_not_found'],
    [422, 'segment_text_invalid'],
  ])('%i lanza SegmentApiError con el código estable', async (status, code) => {
    stubFetch({ detail: { code, message: 'x' } }, status)

    const error = await updateSegment('s1', { text: 'a', revision: 1 }).catch(
      (e: unknown) => e,
    )

    expect(error).toBeInstanceOf(SegmentApiError)
    expect((error as SegmentApiError).code).toBe(code)
  })

  it('un 409 sin segmento actual válido es respuesta inválida', async () => {
    stubFetch({ detail: { code: 'segment_revision_conflict' } }, 409)

    await expect(
      updateSegment('s1', { text: 'a', revision: 1 }),
    ).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('un fallo de red se traduce a network_error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('boom')))

    await expect(
      updateSegment('s1', { text: 'a', revision: 1 }),
    ).rejects.toMatchObject({ code: 'network_error' })
  })

  it('propaga el aborto sin convertirlo', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new DOMException('x', 'AbortError')),
    )

    await expect(
      updateSegment('s1', { text: 'a', revision: 1 }),
    ).rejects.toBeInstanceOf(DOMException)
  })
})
