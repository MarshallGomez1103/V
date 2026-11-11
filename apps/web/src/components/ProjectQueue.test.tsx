import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { QueueView } from '../api/transcriptionQueue'
import { setLang } from '../i18n/i18n'
import type { DiarizationRequest } from './DiarizationOptions'
import { ProjectQueue } from './ProjectQueue'

const diar = vi.hoisted(() => ({ status: 'ready' }))

vi.mock('../hooks/useDiarizationModel', () => ({ useDiarizationModel: () => ({ status: diar.status }) }))
vi.mock('./DiarizationOptions', () => ({
  DiarizationOptions: ({ onChange }: { onChange: (value: DiarizationRequest) => void }) => (
    <input
      type="checkbox"
      aria-label="Diarization control"
      onChange={(event) => {
        onChange({ enabled: event.target.checked, speakers: {} })
      }}
    />
  ),
}))
vi.mock('./TranscriptionOptionsSelector', () => ({
  TranscriptionOptionsSelector: ({ onChange }: { onChange: (id: string | null) => void }) => (
    <button
      onClick={() => {
        onChange('opaque-fw')
      }}
    >
      Choose local
    </button>
  ),
}))

const QUEUE_URL = '/api/projects/p1/transcription-queue'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

type Status = 'pending' | 'running' | 'done' | 'error' | 'cancelled'

const JOB_STATE = {
  pending: 'QUEUED',
  running: 'TRANSCRIBING',
  done: 'COMPLETED',
  error: 'FAILED',
  cancelled: 'CANCELLED',
} as const

const item = (position: number, status: Status, extra: Record<string, unknown> = {}) => ({
  position,
  media_asset_id: 'm' + position,
  filename: 'clase-' + (position + 1) + '.wav',
  job_id: 'j' + position,
  status,
  job_state: JOB_STATE[status],
  progress: status === 'done' ? 1 : status === 'running' ? 0.4 : 0,
  error_code: status === 'error' ? 'transcription_failed' : null,
  transcript_id: status === 'done' ? 't' + position : null,
  ...extra,
})

const SKIPPED = [
  { media_asset_id: 's1', filename: 'vieja.wav', reason: 'already_transcribed' },
  { media_asset_id: 's2', filename: 'rota.wav', reason: 'duration_unknown' },
]

/** Cola de diez ítems: 3 hechos, 1 con error, 1 en curso y 5 en espera; 2 omitidas. */
function queueView(overrides: Partial<QueueView> = {}): QueueView {
  const statuses: Status[] = [
    'done', 'done', 'done', 'error', 'running', 'pending', 'pending', 'pending', 'pending', 'pending',
  ]
  return {
    id: 'q1',
    project_id: 'p1',
    created_at: '2026-11-11T10:00:00Z',
    state: 'running',
    progress: 0.46,
    counts: { total: 10, pending: 5, running: 1, done: 3, error: 1, cancelled: 0, skipped: 2 },
    items: statuses.map((status, position) => item(position, status)),
    skipped: SKIPPED,
    ...overrides,
  }
}

const finishedView = () =>
  queueView({
    state: 'finished',
    progress: 1,
    counts: { total: 10, pending: 0, running: 0, done: 9, error: 1, cancelled: 0, skipped: 2 },
    items: queueView().items.map((entry) =>
      entry.status === 'error' ? entry : (item(entry.position, 'done') as QueueView['items'][number]),
    ),
  })

type Route = (url: string, method: string, body: unknown) => Response | undefined

function stubFetch(route: Route) {
  const fetchMock = vi.fn((input: string, init?: RequestInit) =>
    Promise.resolve(
      route(input, init?.method ?? 'GET', typeof init?.body === 'string' ? JSON.parse(init.body) : undefined) ??
        json({}, 500),
    ),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const callsTo = (fetchMock: ReturnType<typeof stubFetch>, method: string, url: string) =>
  fetchMock.mock.calls.filter(([input, init]) => input === url && (init?.method ?? 'GET') === method)

const renderQueue = (props: Partial<Parameters<typeof ProjectQueue>[0]> = {}) =>
  render(<ProjectQueue projectId="p1" modelsVersion={0} onOpenJob={vi.fn()} {...props} />)

async function tick(ms = 1000) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

beforeEach(() => {
  diar.status = 'ready'
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  setLang('es')
})

describe('ProjectQueue', () => {
  it('muestra conteos y estado por ítem', async () => {
    stubFetch((url) => (url === QUEUE_URL ? json({ queue: queueView() }) : undefined))
    renderQueue()

    expect(
      await screen.findByText('3 de 10 terminadas · 1 con error · 2 omitidas (1 ya transcrita, 1 sin duración)'),
    ).toBeDefined()
    expect(screen.getByRole('progressbar', { name: 'Progreso de la cola' }).getAttribute('aria-valuenow')).toBe('46')

    const table = screen.getByRole('table', { name: 'Grabaciones de la cola' })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(10)
    expect(within(rows[0] as HTMLElement).getByText('clase-1.wav')).toBeDefined()
    expect(within(rows[0] as HTMLElement).getByText('Transcripción completada')).toBeDefined()
    expect(within(rows[3] as HTMLElement).getByText('La transcripción falló')).toBeDefined()
    expect(within(rows[4] as HTMLElement).getByText('Transcribiendo el audio · 40 %')).toBeDefined()
    expect(within(rows[5] as HTMLElement).getByText('En cola, esperando turno')).toBeDefined()
    // Las omitidas se nombran con su motivo.
    expect(screen.getByText('vieja.wav')).toBeDefined()
    expect(screen.getByText('Ya transcrita')).toBeDefined()
    expect(screen.getByText('Sin duración conocida')).toBeDefined()
  })

  it('en inglés habla inglés', async () => {
    setLang('en')
    stubFetch((url) => (url === QUEUE_URL ? json({ queue: queueView() }) : undefined))
    renderQueue()

    expect(
      await screen.findByText('3 of 10 done · 1 failed · 2 skipped (1 already transcribed, 1 without duration)'),
    ).toBeDefined()
    expect(screen.getByRole('button', { name: 'Cancel queue' })).toBeDefined()
  })

  it('sondea cada segundo mientras corre y se detiene al terminar', async () => {
    vi.useFakeTimers()
    const onChanged = vi.fn()
    const responses = [queueView(), queueView(), finishedView()]
    const fetchMock = stubFetch((url) => (url === QUEUE_URL ? json({ queue: responses.shift() ?? finishedView() }) : undefined))
    renderQueue({ onChanged })
    await tick(0)
    expect(callsTo(fetchMock, 'GET', QUEUE_URL)).toHaveLength(1)
    expect(onChanged).not.toHaveBeenCalled()

    await tick(1000)
    expect(callsTo(fetchMock, 'GET', QUEUE_URL)).toHaveLength(2)
    await tick(1000)
    expect(callsTo(fetchMock, 'GET', QUEUE_URL)).toHaveLength(3)
    expect(screen.getByText(/9 de 10 terminadas/)).toBeDefined()
    expect(onChanged).toHaveBeenCalledTimes(1)

    await tick(5000)
    expect(callsTo(fetchMock, 'GET', QUEUE_URL)).toHaveLength(3)
    expect(screen.queryByRole('button', { name: 'Cancelar cola' })).toBeNull()
  })

  it('no sondea una cola que ya terminó al abrir la pantalla', async () => {
    vi.useFakeTimers()
    const onChanged = vi.fn()
    const fetchMock = stubFetch((url) => (url === QUEUE_URL ? json({ queue: finishedView() }) : undefined))
    renderQueue({ onChanged })
    await tick(0)
    await tick(5000)

    expect(callsTo(fetchMock, 'GET', QUEUE_URL)).toHaveLength(1)
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('al desmontar deja de sondear', async () => {
    vi.useFakeTimers()
    const fetchMock = stubFetch((url) => (url === QUEUE_URL ? json({ queue: queueView() }) : undefined))
    const view = renderQueue()
    await tick(0)
    await tick(1000)
    expect(callsTo(fetchMock, 'GET', QUEUE_URL)).toHaveLength(2)

    view.unmount()
    await tick(5000)
    expect(callsTo(fetchMock, 'GET', QUEUE_URL)).toHaveLength(2)
  })

  it('«Cancelar cola» llama a la ruta de la cola y muestra la respuesta', async () => {
    const cancelled = queueView({
      state: 'finished',
      counts: { total: 10, pending: 0, running: 0, done: 3, error: 1, cancelled: 6, skipped: 2 },
    })
    const fetchMock = stubFetch((url, method) => {
      if (url === QUEUE_URL) {
        return json({ queue: queueView() })
      }
      return url === '/api/transcription-queues/q1/cancel' && method === 'POST' ? json(cancelled, 202) : undefined
    })
    renderQueue()

    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar cola' }))

    expect(
      await screen.findByText(
        '3 de 10 terminadas · 1 con error · 6 canceladas · 2 omitidas (1 ya transcrita, 1 sin duración)',
      ),
    ).toBeDefined()
    expect(callsTo(fetchMock, 'POST', '/api/transcription-queues/q1/cancel')).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'Cancelar cola' })).toBeNull()
  })

  it('si la cola ya había terminado al cancelar, lo dice y refresca', async () => {
    let finished = false
    const fetchMock = stubFetch((url, method) => {
      if (url === QUEUE_URL) {
        return json({ queue: finished ? finishedView() : queueView() })
      }
      if (method === 'POST') {
        finished = true
        return json({ detail: { code: 'transcription_queue_finished', message: 'x' } }, 409)
      }
      return undefined
    })
    renderQueue()

    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar cola' }))

    expect(await screen.findByText(/9 de 10 terminadas/)).toBeDefined()
    expect(callsTo(fetchMock, 'GET', QUEUE_URL)).toHaveLength(2)
    // Ya terminada: el aviso de cancelación no se queda pegado.
    expect(screen.queryByText('La cola ya terminó y no se puede cancelar.')).toBeNull()
  })

  it('un error de acción no sobrevive al cambio de cola', async () => {
    let queue = queueView()
    stubFetch((url, method) => {
      if (url === QUEUE_URL) {
        return json({ queue })
      }
      return method === 'POST' && url === '/api/jobs/j6/cancel'
        ? json({ detail: { code: 'job_not_found', message: 'x' } }, 404)
        : undefined
    })
    vi.useFakeTimers()
    renderQueue()
    await tick(0)

    fireEvent.click(screen.getByRole('button', { name: 'Cancelar clase-7.wav' }))
    await tick(0)
    expect(screen.getByText('No se pudo cancelar')).toBeDefined()

    queue = { ...queueView(), id: 'q2' }
    await tick(1000)
    expect(screen.queryByText('No se pudo cancelar')).toBeNull()
  })

  it('la barra de una cola terminada con errores se marca como error', async () => {
    stubFetch((url) => (url === QUEUE_URL ? json({ queue: finishedView() }) : undefined))
    renderQueue()

    await screen.findByText(/9 de 10 terminadas/)
    expect(document.querySelector('.cds--progress-bar--error')).not.toBeNull()
    expect(document.querySelector('.cds--progress-bar--finished')).toBeNull()
  })

  it('la barra de una cola terminada sin errores se marca como terminada', async () => {
    const clean = queueView({
      state: 'finished',
      progress: 1,
      counts: { total: 2, pending: 0, running: 0, done: 2, error: 0, cancelled: 0, skipped: 0 },
      items: [item(0, 'done'), item(1, 'done')] as QueueView['items'],
      skipped: [],
    })
    stubFetch((url) => (url === QUEUE_URL ? json({ queue: clean }) : undefined))
    renderQueue()

    await screen.findByText(/2 de 2 terminadas/)
    expect(document.querySelector('.cds--progress-bar--finished')).not.toBeNull()
    expect(document.querySelector('.cds--progress-bar--error')).toBeNull()
  })

  it('tras tres sondeos fallidos avisa, sigue sondeando y quita el aviso al recuperarse', async () => {
    vi.useFakeTimers()
    let failures = 0
    const fetchMock = stubFetch((url) => {
      if (url !== QUEUE_URL) {
        return undefined
      }
      if (callsTo(fetchMock, 'GET', QUEUE_URL).length > 1 && failures < 3) {
        failures += 1
        return json({}, 500)
      }
      return json({ queue: queueView() })
    })
    renderQueue()
    await tick(0)
    await tick(1000)
    await tick(1000)
    expect(screen.queryByText('No se pudo consultar la cola')).toBeNull()

    await tick(1000)
    expect(screen.getByText('No se pudo consultar la cola')).toBeDefined()

    await tick(1000)
    expect(screen.queryByText('No se pudo consultar la cola')).toBeNull()
    expect(callsTo(fetchMock, 'GET', QUEUE_URL)).toHaveLength(5)
  })

  it('al iniciar con el teclado el foco pasa al resumen de la cola', async () => {
    stubFetch((url, method) => {
      if (url === QUEUE_URL && method === 'GET') {
        return json({ queue: null })
      }
      return url === QUEUE_URL && method === 'POST' ? json(queueView(), 201) : undefined
    })
    renderQueue()

    fireEvent.click(await screen.findByRole('button', { name: 'Choose local' }))
    const start = screen.getByRole('button', { name: 'Transcribir proyecto' })
    start.focus()
    fireEvent.click(start)

    const summary = await screen.findByText(/3 de 10 terminadas/)
    await vi.waitFor(() => {
      expect(document.activeElement).toBe(summary)
    })
  })

  it('si «Cancelar cola» tenía el foco y desaparece, el foco pasa al resumen', async () => {
    stubFetch((url, method) => {
      if (url === QUEUE_URL) {
        return json({ queue: queueView() })
      }
      return method === 'POST' && url === '/api/transcription-queues/q1/cancel'
        ? json(queueView({ state: 'finished' }), 202)
        : undefined
    })
    renderQueue()

    const cancel = await screen.findByRole('button', { name: 'Cancelar cola' })
    cancel.focus()
    fireEvent.click(cancel)

    await vi.waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Cancelar cola' })).toBeNull()
      expect(document.activeElement).toBe(screen.getByText(/3 de 10 terminadas/))
    })
  })

  it('no roba el foco si la cola termina sola y el foco está en otro sitio', async () => {
    vi.useFakeTimers()
    const responses = [queueView(), finishedView()]
    stubFetch((url) => (url === QUEUE_URL ? json({ queue: responses.shift() ?? finishedView() }) : undefined))
    renderQueue()
    await tick(0)
    const other = screen.getByRole('link', { name: 'Abrir clase-1.wav' })
    other.focus()
    await tick(1000)

    expect(document.activeElement).toBe(other)
  })

  it('«Cancelar» de un ítem usa la ruta del trabajo y refresca la cola', async () => {
    const fetchMock = stubFetch((url, method) => {
      if (url === QUEUE_URL) {
        return json({ queue: queueView() })
      }
      return url === '/api/jobs/j6/cancel' && method === 'POST'
        ? json({
            id: 'j6', project_id: 'p1', media_asset_id: 'm6', state: 'CANCELLED', progress: 0,
            error_code: null, transcript_id: null, created_at: 'a', updated_at: 'b',
          }, 202)
        : undefined
    })
    renderQueue()

    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar clase-7.wav' }))

    await vi.waitFor(() => {
      expect(callsTo(fetchMock, 'POST', '/api/jobs/j6/cancel')).toHaveLength(1)
      expect(callsTo(fetchMock, 'GET', QUEUE_URL)).toHaveLength(2)
    })
    // Los hechos y con error no se cancelan.
    expect(screen.queryByRole('button', { name: 'Cancelar clase-1.wav' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Cancelar clase-4.wav' })).toBeNull()
  })

  it('«Abrir» solo está en los terminados y abre su trabajo', async () => {
    const onOpenJob = vi.fn()
    stubFetch((url) => (url === QUEUE_URL ? json({ queue: queueView() }) : undefined))
    renderQueue({ onOpenJob })

    const link = await screen.findByRole('link', { name: 'Abrir clase-2.wav' })
    expect(link.getAttribute('href')).toBe('#/t/j1')
    expect(screen.getAllByRole('link')).toHaveLength(3)
    fireEvent.click(link)
    expect(onOpenJob).toHaveBeenCalledWith('j1')
  })

  describe('iniciar la cola', () => {
    const idle = () => stubFetch((url, method, body) => {
      if (url === QUEUE_URL && method === 'GET') {
        return json({ queue: null })
      }
      if (url === QUEUE_URL && method === 'POST') {
        return body ? json(queueView(), 201) : undefined
      }
      return undefined
    })

    it('sin motor elegido no se puede iniciar y dice por qué', async () => {
      idle()
      renderQueue()

      const start = await screen.findByRole('button', { name: 'Transcribir proyecto' })
      expect(start).toHaveProperty('disabled', true)
      expect(screen.getByText('Elige un motor para poder transcribir.')).toBeDefined()
    })

    it('crea la cola con la opción local y los hablantes elegidos, y muestra su estado', async () => {
      const fetchMock = idle()
      renderQueue()

      fireEvent.click(await screen.findByRole('button', { name: 'Choose local' }))
      fireEvent.click(screen.getByRole('checkbox', { name: 'Diarization control' }))
      fireEvent.click(screen.getByRole('button', { name: 'Transcribir proyecto' }))

      expect(await screen.findByText(/3 de 10 terminadas/)).toBeDefined()
      const [, init] = callsTo(fetchMock, 'POST', QUEUE_URL)[0] ?? []
      expect(JSON.parse(init?.body as string)).toEqual({
        option_id: 'opaque-fw',
        language: null,
        diarization: { enabled: true, speakers: {} },
      })
      // Mientras corre no se ofrece iniciar otra.
      expect(screen.queryByRole('button', { name: 'Transcribir proyecto' })).toBeNull()
    })

    it('con hablantes activados espera al modelo antes de iniciar', async () => {
      diar.status = 'missing'
      idle()
      renderQueue()

      fireEvent.click(await screen.findByRole('button', { name: 'Choose local' }))
      fireEvent.click(screen.getByRole('checkbox', { name: 'Diarization control' }))

      expect(screen.getByRole('button', { name: 'Transcribir proyecto' })).toHaveProperty('disabled', true)
      expect(screen.getByText(/Transcribir se activa cuando el modelo de hablantes/)).toBeDefined()
    })

    it('un 409 de cola vacía muestra las omitidas con su motivo', async () => {
      stubFetch((url, method) => {
        if (url === QUEUE_URL && method === 'GET') {
          return json({ queue: null })
        }
        return json(
          { detail: { code: 'transcription_queue_empty', message: 'x', skipped: SKIPPED } },
          409,
        )
      })
      renderQueue()

      fireEvent.click(await screen.findByRole('button', { name: 'Choose local' }))
      fireEvent.click(screen.getByRole('button', { name: 'Transcribir proyecto' }))

      expect(await screen.findByText('No se pudo iniciar la cola')).toBeDefined()
      expect(screen.getByText('Ninguna grabación se puede transcribir ahora: todas se omitieron.')).toBeDefined()
      expect(screen.getByText('vieja.wav')).toBeDefined()
      expect(screen.getByText('Ya transcrita')).toBeDefined()
      expect(screen.getByText('rota.wav')).toBeDefined()
      expect(screen.getByText('Sin duración conocida')).toBeDefined()
      // La pantalla sigue lista para otro intento.
      expect(screen.getByRole('button', { name: 'Transcribir proyecto' })).toHaveProperty('disabled', false)
    })

    it('traduce el rechazo de la nube del servidor, sin mostrar su código', async () => {
      stubFetch((url, method) =>
        url === QUEUE_URL && method === 'GET'
          ? json({ queue: null })
          : json({ detail: { code: 'transcription_queue_cloud_unsupported', message: 'x' } }, 422),
      )
      renderQueue()

      fireEvent.click(await screen.findByRole('button', { name: 'Choose local' }))
      fireEvent.click(screen.getByRole('button', { name: 'Transcribir proyecto' }))

      expect(await screen.findByText(/La cola solo admite motores locales\. Elige una opción/)).toBeDefined()
      expect(screen.queryByText(/transcription_queue_cloud_unsupported/)).toBeNull()
    })
  })

  it('si falla la consulta de la cola, lo dice y deja reintentar', async () => {
    let attempts = 0
    stubFetch((url) => {
      if (url !== QUEUE_URL) {
        return undefined
      }
      attempts += 1
      return attempts === 1
        ? json({ detail: { code: 'project_not_found', message: 'x' } }, 404)
        : json({ queue: null })
    })
    renderQueue()

    expect(await screen.findByText('No se pudo consultar la cola')).toBeDefined()
    expect(screen.getByText('El proyecto ya no existe.')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: /reintentar/i }))
    expect(await screen.findByRole('button', { name: 'Transcribir proyecto' })).toBeDefined()
  })

  it('si la consulta inicial falla por red, no muestra un código genérico', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))))
    renderQueue()

    expect(await screen.findByText('No se pudo consultar la cola')).toBeDefined()
    expect(screen.getByText('No se pudo conectar con el servidor.')).toBeDefined()
    expect(screen.queryByText(/generic/)).toBeNull()
  })
})
