import { afterEach, describe, expect, it, vi } from 'vitest'

import { GlossaryError, getGlossary, putGlossary } from './glossary'

afterEach(() => {
  vi.unstubAllGlobals()
})

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response
}

const GLOSSARY = {
  terms: ['Mitocondria'],
  max_terms: 50,
  max_term_length: 50,
  applies_to: ['faster-whisper'],
}

describe('glossary api', () => {
  it('GET lee el glosario del proyecto', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(200, GLOSSARY))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getGlossary('p 1')).resolves.toEqual(GLOSSARY)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/projects/p%201/glossary')
  })

  it('PUT envía los términos y devuelve la versión normalizada', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(200, GLOSSARY))
    vi.stubGlobal('fetch', fetchMock)

    await putGlossary('p1', ['Mitocondria'])

    const init = fetchMock.mock.calls[0]?.[1]
    expect(init?.method).toBe('PUT')
    expect(init?.body).toBe(JSON.stringify({ terms: ['Mitocondria'] }))
  })

  it('traduce el código estable de error a un mensaje en español', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse(422, { detail: { code: 'glossary_invalid', message: 'x' } }),
      ),
    )

    const error = await putGlossary('p1', ['x']).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(GlossaryError)
    expect((error as GlossaryError).code).toBe('glossary_invalid')
    expect((error as GlossaryError).message).toContain('glosario no es válido')
  })

  it('rechaza una respuesta con forma inesperada', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(200, { terms: 'no' })),
    )

    await expect(getGlossary('p1')).rejects.toMatchObject({ code: 'invalid_response' })
  })
})
