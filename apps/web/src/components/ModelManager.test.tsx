import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import type { ModelView, TaskView } from '../api/models'
import { ModelManager } from './ModelManager'

beforeAll(() => {
  // jsdom no implementa <dialog> modal: basta con alternar el atributo `open`.
  HTMLDialogElement.prototype.showModal = function showModal() {
    this.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.close = function close() {
    this.removeAttribute('open')
  }
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response
}

function model(overrides: Partial<ModelView> & Pick<ModelView, 'model_id'>): ModelView {
  return {
    display_name: 'Faster Whisper ' + overrides.model_id,
    source: 'Systran/faster-whisper-' + overrides.model_id,
    revision: 'abc123',
    license: 'MIT',
    multilingual: true,
    profile: 'fast',
    size_bytes: 1_600_000_000,
    installed: false,
    disk_bytes: null,
    external: [],
    ...overrides,
  }
}

function task(overrides: Partial<TaskView> = {}): TaskView {
  return {
    id: 't1',
    model_id: 'turbo',
    method: 'download',
    origin: null,
    state: 'running',
    done_bytes: 400_000_000,
    total_bytes: 1_600_000_000,
    error_code: null,
    created_at: '2026-09-30T10:00:00Z',
    updated_at: '2026-09-30T10:00:01Z',
    ...overrides,
  }
}

const DISK = { models_bytes: 77_003_619, free_bytes: 50_000_000_000 }

type Handler = (url: string, init: RequestInit | undefined) => Response | undefined

/** Enruta por URL; cada handler devuelve undefined si no le corresponde. */
function stubApi(...handlers: Handler[]) {
  const fetchMock = vi.fn<typeof fetch>((input, init) => {
    const url = input as string
    for (const handler of handlers) {
      const response = handler(url, init)
      if (response) {
        return Promise.resolve(response)
      }
    }
    return Promise.reject(new Error('fetch inesperado: ' + url))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const models =
  (list: ModelView[], disk = DISK): Handler =>
  (url, init) =>
    url === '/api/models' && !init?.method
      ? jsonResponse(200, { models: list, disk })
      : undefined

const tasks =
  (list: TaskView[]): Handler =>
  (url, init) =>
    url === '/api/model-tasks' && !init?.method
      ? jsonResponse(200, { tasks: list })
      : undefined

describe('ModelManager', () => {
  it('lista los modelos en orden de catálogo con tamaño, perfil, licencia y disco', async () => {
    stubApi(
      models([
        model({ model_id: 'tiny', size_bytes: 77_003_619, installed: true, disk_bytes: 77_003_619 }),
        model({ model_id: 'large-v3', profile: 'quality' }),
        model({ model_id: 'turbo' }),
      ]),
      tasks([]),
    )

    render(<ModelManager />)

    expect(await screen.findByRole('heading', { level: 2, name: 'Modelos' })).toBeDefined()
    const headings = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)
    expect(headings).toEqual([
      'Faster Whisper turbo',
      'Faster Whisper large-v3',
      'Faster Whisper tiny',
    ])
    expect(screen.getByText('Recomendado')).toBeDefined()
    expect(screen.getByText('Calidad')).toBeDefined()
    expect(screen.getAllByRole('button', { name: /descargar \(1,6\sGB\)/i })).toHaveLength(2)
    expect(screen.getByText('Instalado')).toBeDefined()
    expect(screen.getByText(/espacio libre/i).textContent).toMatch(/50\sGB/)
    expect(screen.getAllByText('MIT').length).toBeGreaterThan(0)
  })

  it('ofrece importar desde Buzz sin descargar y avisa al terminar', async () => {
    let installBody: unknown
    let listed = 0
    const onModelsChanged = vi.fn()
    stubApi(
      (url, init) => {
        if (url === '/api/models/tiny/install' && init?.method === 'POST') {
          installBody = JSON.parse(init.body as string)
          return jsonResponse(
            202,
            task({ id: 'imp', model_id: 'tiny', method: 'import', origin: 'buzz', state: 'queued' }),
          )
        }
        return undefined
      },
      (url, init) => {
        if (url === '/api/model-tasks' && !init?.method) {
          listed += 1
          // 1.ª lectura: vacía; después la tarea ya está completada.
          return jsonResponse(200, {
            tasks:
              listed < 2
                ? []
                : [task({ id: 'imp', model_id: 'tiny', method: 'import', origin: 'buzz', state: 'completed' })],
          })
        }
        return undefined
      },
      models([model({ model_id: 'tiny', external: [{ origin: 'buzz' }] })]),
    )

    render(<ModelManager onModelsChanged={onModelsChanged} />)

    expect(await screen.findByText('Disponible en Buzz')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: /importar desde buzz/i }))

    await waitFor(() => {
      expect(onModelsChanged).toHaveBeenCalledTimes(1)
    })
    expect(installBody).toEqual({ method: 'import', origin: 'buzz', confirm: true })
  })

  it('no ofrece importar si Buzz no tiene el modelo', async () => {
    stubApi(models([model({ model_id: 'tiny' })]), tasks([]))
    render(<ModelManager />)
    await screen.findByRole('button', { name: /descargar/i })
    expect(screen.queryByRole('button', { name: /importar desde buzz/i })).toBeNull()
  })

  it('pide confirmación con tamaño y origen antes de descargar', async () => {
    let installBody: unknown
    const fetchMock = stubApi(
      (url, init) => {
        if (url === '/api/models/turbo/install' && init?.method === 'POST') {
          installBody = JSON.parse(init.body as string)
          return jsonResponse(202, task({ state: 'queued', done_bytes: 0 }))
        }
        return undefined
      },
      models([model({ model_id: 'turbo' })]),
      tasks([]),
    )

    render(<ModelManager />)
    fireEvent.click(await screen.findByRole('button', { name: /descargar \(1,6\sGB\)/i }))

    const dialog = await screen.findByRole('dialog', { name: /descargar faster whisper turbo/i })
    expect(dialog.textContent).toMatch(/1,6\sGB/)
    expect(dialog.textContent).toMatch(/HuggingFace/)
    expect(fetchMock.mock.calls.some(([u]) => (u as string).includes('/install'))).toBe(false)
    expect(document.activeElement).toBe(within(dialog).getByRole('button', { name: 'Descargar' }))

    fireEvent.click(within(dialog).getByRole('button', { name: 'Descargar' }))

    await waitFor(() => {
      expect(installBody).toEqual({ method: 'download', confirm: true })
    })
    expect(await screen.findByRole('status')).toBeDefined()
  })

  it('cancelar el diálogo de descarga no instala nada', async () => {
    const fetchMock = stubApi(models([model({ model_id: 'turbo' })]), tasks([]))

    render(<ModelManager />)
    fireEvent.click(await screen.findByRole('button', { name: /descargar \(1,6\sGB\)/i }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancelar' }))

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull()
    })
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
  })

  it('muestra progreso con porcentaje y bytes, y permite cancelar', async () => {
    let cancelled = false
    stubApi(
      (url, init) => {
        if (url === '/api/model-tasks/t1/cancel' && init?.method === 'POST') {
          cancelled = true
          return jsonResponse(202, task({ state: 'cancelled' }))
        }
        return undefined
      },
      (url, init) =>
        url === '/api/model-tasks' && !init?.method
          ? jsonResponse(200, { tasks: [task({ state: cancelled ? 'cancelled' : 'running' })] })
          : undefined,
      models([model({ model_id: 'turbo' })]),
    )

    render(<ModelManager />)

    const status = await screen.findByRole('status')
    expect(status.textContent).toMatch(/25 %/)
    expect(status.textContent).toMatch(/400\sMB de 1,6\sGB/)
    const bar = within(status).getByRole('progressbar')
    expect(bar.getAttribute('value')).toBe('400000000')

    fireEvent.click(within(status).getByRole('button', { name: 'Cancelar' }))

    expect(await screen.findByText('Instalación cancelada.')).toBeDefined()
    expect(screen.queryByRole('status')).toBeNull()
  })

  it.each([
    ['disk_space_insufficient', /no hay espacio libre suficiente/i],
    ['model_installation_network_error', /revisa tu conexión/i],
    ['model_installation_checksum_mismatch', /suma de verificación/i],
    ['algo_raro', /código algo_raro/i],
  ])('explica en español la tarea fallida %s', async (code, expected) => {
    stubApi(
      models([model({ model_id: 'turbo' })]),
      tasks([task({ state: 'failed', error_code: code })]),
    )

    render(<ModelManager />)

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toMatch(expected)
  })

  it('explica el error 409 al iniciar una instalación y refresca la lista', async () => {
    const fetchMock = stubApi(
      (url, init) =>
        url === '/api/models/turbo/install' && init?.method === 'POST'
          ? jsonResponse(409, {
              detail: { code: 'model_already_installed', message: 'x' },
            })
          : undefined,
      models([model({ model_id: 'turbo' })]),
      tasks([]),
    )

    render(<ModelManager />)
    fireEvent.click(await screen.findByRole('button', { name: /descargar \(1,6\sGB\)/i }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Descargar' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toMatch(/ya está instalado/i)
    await waitFor(() => {
      const listCalls = fetchMock.mock.calls.filter(([u]) => (u as string) === '/api/models')
      expect(listCalls.length).toBe(2)
    })
  })

  it('exige escribir el id para eliminar y refresca al borrar', async () => {
    let deleteUrl = ''
    let deleted = false
    const onModelsChanged = vi.fn()
    stubApi(
      (url, init) => {
        if (url.startsWith('/api/models/tiny') && init?.method === 'DELETE') {
          deleteUrl = url
          deleted = true
          return jsonResponse(200, { model_id: 'tiny', freed_bytes: 77_003_619 })
        }
        return undefined
      },
      (url, init) =>
        url === '/api/models' && !init?.method
          ? jsonResponse(200, {
              models: [
                deleted
                  ? model({ model_id: 'tiny' })
                  : model({ model_id: 'tiny', installed: true, disk_bytes: 77_003_619 }),
              ],
              disk: DISK,
            })
          : undefined,
      tasks([]),
    )

    render(<ModelManager onModelsChanged={onModelsChanged} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }))

    const dialog = await screen.findByRole('dialog', { name: /eliminar faster whisper tiny/i })
    const input = within(dialog).getByLabelText(/escribe/i)
    expect(document.activeElement).toBe(input)
    const confirm = within(dialog).getByRole('button', { name: 'Eliminar' })
    expect(confirm).toHaveProperty('disabled', true)

    fireEvent.change(input, { target: { value: 'tin' } })
    expect(confirm).toHaveProperty('disabled', true)
    fireEvent.change(input, { target: { value: 'tiny' } })
    expect(confirm).toHaveProperty('disabled', false)
    fireEvent.click(confirm)

    await waitFor(() => {
      expect(onModelsChanged).toHaveBeenCalledTimes(1)
    })
    expect(deleteUrl).toBe('/api/models/tiny?confirm=tiny')
    expect(await screen.findByRole('button', { name: /descargar/i })).toBeDefined()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('explica model_in_use dentro del diálogo de borrado', async () => {
    stubApi(
      (url, init) =>
        url.startsWith('/api/models/tiny') && init?.method === 'DELETE'
          ? jsonResponse(409, { detail: { code: 'model_in_use', message: 'x' } })
          : undefined,
      models([model({ model_id: 'tiny', installed: true, disk_bytes: 1000 })]),
      tasks([]),
    )

    render(<ModelManager />)
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText(/escribe/i), {
      target: { value: 'tiny' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Eliminar' }))

    const alert = await within(dialog).findByRole('alert')
    expect(alert.textContent).toMatch(/en uso por una transcripción/i)
    expect(screen.getByRole('dialog')).toBeDefined()
  })

  it('muestra error de carga con reintento', async () => {
    let attempts = 0
    stubApi(
      (url, init) => {
        if (url === '/api/models' && !init?.method) {
          attempts += 1
          return attempts === 1
            ? jsonResponse(500, { detail: { code: 'boom', message: 'x' } })
            : jsonResponse(200, { models: [model({ model_id: 'tiny' })], disk: DISK })
        }
        return undefined
      },
      tasks([]),
    )

    render(<ModelManager />)
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toMatch(/código boom/i)
    fireEvent.click(within(alert).getByRole('button', { name: /reintentar/i }))
    expect(await screen.findByRole('heading', { level: 3 })).toBeDefined()
  })

  it('no ofrece acciones de instalación sobre un modelo con tarea activa', async () => {
    stubApi(models([model({ model_id: 'turbo' })]), tasks([task()]))
    render(<ModelManager />)
    await screen.findByRole('status')
    expect(screen.queryByRole('button', { name: /descargar/i })).toBeNull()
  })
})
