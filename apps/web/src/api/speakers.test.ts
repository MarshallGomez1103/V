import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  assignSegmentSpeaker,
  listSpeakers,
  mergeSpeakers,
  rediarize,
  SpeakerApiError,
  updateSpeaker,
} from './speakers'

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

const ANA = { id: 'a', name: 'Ana', color: '#112233', segment_count: 2 }

describe('api/speakers', () => {
  it('listSpeakers hace GET y devuelve los hablantes', async () => {
    const fetchMock = stubFetch({ speakers: [ANA] })

    await expect(listSpeakers('t/1')).resolves.toEqual([ANA])
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/transcripts/t%2F1/speakers',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('listSpeakers rechaza una forma inesperada', async () => {
    stubFetch({ speakers: [{ id: 'a' }] })

    await expect(listSpeakers('t')).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })

  it('updateSpeaker hace PATCH con los cambios', async () => {
    const fetchMock = stubFetch(ANA)

    await expect(updateSpeaker('a', { name: 'Ana' })).resolves.toEqual(ANA)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/speakers/a',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ name: 'Ana' }),
      }),
    )
  })

  it('mergeSpeakers hace POST y devuelve el destino', async () => {
    const fetchMock = stubFetch({ speaker: ANA })

    await expect(mergeSpeakers('b', 'a')).resolves.toEqual(ANA)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/speakers/b/merge',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ into: 'a' }),
      }),
    )
  })

  it('assignSegmentSpeaker hace PUT con speaker_id (o null)', async () => {
    const fetchMock = stubFetch({ id: 's1', speaker_id: null })

    await assignSegmentSpeaker('s1', null)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/segments/s1/speaker',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ speaker_id: null }),
      }),
    )
  })

  it.each([
    [422, 'speaker_update_invalid'],
    [404, 'speaker_not_found'],
    [409, 'speaker_merge_invalid'],
  ])('%i lanza SpeakerApiError con el código estable', async (status, code) => {
    stubFetch({ detail: { code, message: 'x' } }, status)

    const error = await updateSpeaker('a', { name: '' }).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(SpeakerApiError)
    expect((error as SpeakerApiError).code).toBe(code)
  })

  it('un fallo de red se traduce a network_error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('boom')))

    await expect(listSpeakers('t')).rejects.toMatchObject({
      code: 'network_error',
    })
  })

  it('propaga el aborto sin convertirlo', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new DOMException('x', 'AbortError')),
    )

    await expect(listSpeakers('t')).rejects.toBeInstanceOf(DOMException)
  })
})

describe('api/speakers: v3', () => {
  it('listSpeakers conserva talk_ms y first_ms cuando el servidor los envía', async () => {
    stubFetch({ speakers: [{ ...ANA, talk_ms: 4000, first_ms: 250 }] })
    await expect(listSpeakers('t')).resolves.toEqual([{ ...ANA, talk_ms: 4000, first_ms: 250 }])
  })

  it('rediarize hace POST con el rango pedido y devuelve el trabajo', async () => {
    const view = {
      id: 'j2',
      project_id: 'p',
      media_asset_id: 'm',
      state: 'DIARIZING',
      progress: 0.1,
      error_code: null,
      transcript_id: 't1',
      created_at: '2026-10-01T10:00:00Z',
      updated_at: '2026-10-01T10:00:00Z',
    }
    const fetchMock = stubFetch(view, 202)
    await expect(rediarize('t/1', { minimum: 2, maximum: 4 })).resolves.toMatchObject({ id: 'j2' })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/transcripts/t%2F1/rediarize',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ speakers: { minimum: 2, maximum: 4 } }),
      }),
    )
  })

  it('rediarize traduce diarization_models_missing', async () => {
    stubFetch({ detail: { code: 'diarization_models_missing', message: 'x' } }, 409)
    await expect(rediarize('t', { exact: 2 })).rejects.toMatchObject({
      code: 'diarization_models_missing',
      message: expect.stringContaining('modelo de hablantes') as string,
    })
  })
})
