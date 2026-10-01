import { afterEach, describe, expect, it, vi } from 'vitest'

import { getQualityProfiles, QualityProfilesError } from './qualityProfiles'

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

const PAYLOAD = {
  default: 'default',
  profiles: [
    {
      name: 'default',
      label: 'Estándar',
      description: 'Por defecto',
      parameters: { name: 'default', version: 1 },
    },
  ],
  recommendation: {
    language: 'es',
    profile: 'default',
    measured: true,
    evidence: 'docs/benchmarks.md',
    synthetic: true,
    unmeasured_profiles: [],
  },
}

describe('getQualityProfiles', () => {
  it('pasa el idioma en la consulta', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(200, PAYLOAD))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getQualityProfiles('es-CO')).resolves.toEqual(PAYLOAD)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/quality-profiles?language=es-CO')

    await getQualityProfiles(null)
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/quality-profiles')
  })

  it('falla con código estable ante HTTP de error o formato inesperado', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValueOnce(jsonResponse(500, {})),
    )
    await expect(getQualityProfiles()).rejects.toMatchObject({ code: 'http_500' })

    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValueOnce(jsonResponse(200, { profiles: 1 })),
    )
    const error = await getQualityProfiles().catch((e: unknown) => e)
    expect(error).toBeInstanceOf(QualityProfilesError)
    expect((error as QualityProfilesError).code).toBe('invalid_response')
  })
})
