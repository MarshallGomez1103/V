import { afterEach, describe, expect, it, vi } from 'vitest'

import { ProjectError } from './projects'
import { fetchRecordings } from './recordings'

afterEach(() => {
  vi.unstubAllGlobals()
})

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const RECORDING = {
  media_asset_id: 'm1',
  filename: 'clase.wav',
  media_type: 'audio',
  duration_ms: 61_000,
  created_at: '2026-11-01T10:00:00Z',
  latest_job: {
    id: 'j1',
    state: 'COMPLETED',
    transcript_id: 't1',
    model_id: 'turbo',
    created_at: '2026-11-01T11:00:00Z',
  },
}

describe('fetchRecordings', () => {
  it('lee las grabaciones del proyecto con su último trabajo', async () => {
    const fetchMock = vi.fn<(url: string) => Promise<Response>>(() =>
      Promise.resolve(
        json({
          recordings: [RECORDING, { ...RECORDING, media_asset_id: 'm2', duration_ms: null, latest_job: null }],
        }),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const recordings = await fetchRecordings('p 1')

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/projects/p%201/recordings')
    expect(recordings).toHaveLength(2)
    expect(recordings[0]).toMatchObject({ media_asset_id: 'm1', latest_job: { id: 'j1', state: 'COMPLETED' } })
    expect(recordings[1]).toMatchObject({ duration_ms: null, latest_job: null })
  })

  it('traduce el 404 project_not_found a un ProjectError con su código', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(json({ detail: { code: 'project_not_found', message: 'x' } }, 404))),
    )
    const error = await fetchRecordings('p1').catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ProjectError)
    expect(error).toMatchObject({ code: 'project_not_found', message: 'El proyecto ya no existe.' })
  })

  it('rechaza una respuesta con forma inválida', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json({ recordings: [{ filename: 3 }] }))))
    await expect(fetchRecordings('p1')).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('ignora un estado de trabajo desconocido en vez de inventarlo', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(json({ recordings: [{ ...RECORDING, latest_job: { ...RECORDING.latest_job, state: 'NOPE' } }] })),
      ),
    )
    const [first] = await fetchRecordings('p1')
    expect(first?.latest_job).toBeNull()
  })
})
