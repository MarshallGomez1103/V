import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchLibrary } from './library'

afterEach(() => {
  vi.unstubAllGlobals()
})

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

describe('fetchLibrary', () => {
  it('lee /api/library con su contrato', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          json({
            items: [
              {
                project_id: 'p1',
                name: 'Clase',
                created_at: '2026-10-01T10:00:00Z',
                media: { media_asset_id: 'a1', filename: 'c.wav', duration_ms: 1000 },
                latest_job: {
                  id: 'j1',
                  state: 'COMPLETED',
                  transcript_id: 't1',
                  model_id: 'turbo',
                  created_at: '2026-10-01T10:00:00Z',
                },
                speaker_count: 2,
                segment_count: 10,
              },
            ],
          }),
        ),
      ),
    )
    const items = await fetchLibrary()
    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({
      project_id: 'p1',
      latest_job: { id: 'j1', state: 'COMPLETED', transcript_id: 't1' },
      speaker_count: 2,
    })
  })

  it('acepta proyectos sin medio ni trabajo', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          json({
            items: [{ project_id: 'p1', name: 'x', created_at: '2026-10-01T10:00:00Z', media: null, latest_job: null }],
          }),
        ),
      ),
    )
    const [first] = await fetchLibrary()
    expect(first).toMatchObject({ media: null, latest_job: null, speaker_count: null })
  })

  it('con 404 compone la biblioteca con proyectos y trabajos', async () => {
    const job = {
      id: 'j1',
      project_id: 'p1',
      media_asset_id: 'a1',
      state: 'COMPLETED',
      progress: 1,
      error_code: null,
      transcript_id: 't1',
      created_at: '2026-10-01T10:00:00Z',
      updated_at: '2026-10-01T10:00:00Z',
      selection: { option_id: 'o', provider_id: 'p', model_id: 'turbo' },
    }
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = (input instanceof Request ? input.url : input.toString())
        if (url === '/api/library') {
          return Promise.resolve(json({}, 404))
        }
        if (url === '/api/projects') {
          return Promise.resolve(json({ projects: [{ id: 'p1', name: 'Clase', created_at: '2026-10-01T10:00:00Z' }] }))
        }
        return Promise.resolve(json({ jobs: [job] }))
      }),
    )
    const [first] = await fetchLibrary()
    expect(first).toMatchObject({
      project_id: 'p1',
      name: 'Clase',
      latest_job: { id: 'j1', transcript_id: 't1', model_id: 'turbo' },
      media: { media_asset_id: 'a1', duration_ms: null },
    })
  })

  it('rechaza una respuesta con forma inválida', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json({ items: [{ nope: 1 }] }))))
    await expect(fetchLibrary()).rejects.toMatchObject({ code: 'invalid_response' })
  })
})
