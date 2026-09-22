import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  JobApiError,
  cancelJob,
  createJob,
  getJob,
  getSegments,
  isJobView,
} from './jobs'

afterEach(() => {
  vi.unstubAllGlobals()
})

const jobBody = {
  id: 'job-1',
  project_id: 'p1',
  media_asset_id: 'a1',
  state: 'QUEUED',
  progress: 0,
  error_code: null,
  transcript_id: null,
  created_at: '2026-09-21T10:00:00Z',
  updated_at: '2026-09-21T10:00:00Z',
}

function stubFetch(body: unknown, ok = true, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(body),
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('api/jobs', () => {
  it('createJob envía el cuerpo y devuelve el JobView', async () => {
    const fetchMock = stubFetch(jobBody, true, 201)
    const input = {
      project_id: 'p1',
      media_asset_id: 'a1',
      option_id: 'o1',
      language: null,
    }

    const job = await createJob(input)

    expect(job.state).toBe('QUEUED')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/jobs',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(input),
      }),
    )
  })

  it('createJob 409 expone code y blocking_reasons con mensaje seguro', async () => {
    stubFetch(
      {
        detail: {
          code: 'option_not_startable',
          message: 'internal detail',
          blocking_reasons: ['model_missing', 'gpu_unavailable'],
        },
      },
      false,
      409,
    )

    const error = await createJob({
      project_id: 'p1',
      media_asset_id: 'a1',
      option_id: 'o1',
      language: 'es',
    }).catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(JobApiError)
    const apiError = error as JobApiError
    expect(apiError.code).toBe('option_not_startable')
    expect(apiError.blockingReasons).toEqual(['model_missing', 'gpu_unavailable'])
    expect(apiError.message).toBe(
      'Esta opción todavía no se puede iniciar en este equipo.',
    )
  })

  it('usa un código http_* cuando el cuerpo de error no sigue el contrato', async () => {
    stubFetch('nope', false, 500)

    const error = await getJob('job-1').catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(JobApiError)
    expect((error as JobApiError).code).toBe('http_500')
  })

  it('rechaza un JobView inválido', async () => {
    stubFetch({ ...jobBody, state: 'WHATEVER' })

    const error = await getJob('job-1').catch((caught: unknown) => caught)

    expect((error as JobApiError).code).toBe('invalid_response')
    expect(isJobView({ ...jobBody, state: 'WHATEVER' })).toBe(false)
    expect(isJobView(jobBody)).toBe(true)
  })

  it('cancelJob hace POST a /cancel con el id codificado', async () => {
    const fetchMock = stubFetch({ ...jobBody, state: 'CANCELLING' }, true, 202)

    const job = await cancelJob('job/1')

    expect(job.state).toBe('CANCELLING')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/jobs/job%2F1/cancel',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('getSegments devuelve la lista y rechaza cuerpos inválidos', async () => {
    stubFetch({ segments: [{ id: 's1', start_ms: 0, end_ms: 10, text: 'a' }] })
    expect(await getSegments('tr-1')).toHaveLength(1)

    stubFetch({ segments: [{ id: 's1' }] })
    const error = await getSegments('tr-1').catch((caught: unknown) => caught)
    expect((error as JobApiError).code).toBe('invalid_response')
  })
})
