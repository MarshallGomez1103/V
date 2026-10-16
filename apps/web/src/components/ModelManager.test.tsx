import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ModelView, TaskView } from '../api/models'
import { setLang } from '../i18n/i18n'
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
    key: 'faster-whisper:' + overrides.model_id,
    provider_id: 'faster-whisper',
    kind: 'asr',
    requires: null,
    runtime_available: true,
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
    key: 'faster-whisper:' + (overrides.model_id ?? 'turbo'),
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

/** Filas de datos de una tabla (sin la fila de encabezados). */
function dataRows(root: HTMLElement | Document = document): HTMLElement[] {
  return within(root as HTMLElement)
    .getAllByRole('row')
    .slice(1)
}

describe('ModelManager', () => {
  it('allows the first ASR import from custom engines even with an empty model catalog', async () => {
    stubApi((url) => url === '/api/models'
      ? jsonResponse(200, { models: [], disk: DISK, custom_engines: ['sherpa-onnx-asr'] })
      : undefined, tasks([]))
    render(<ModelManager />)
    await waitFor(() => { expect(document.querySelector('.voz-models__disk')).not.toBeNull() })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Añadir modelo propio' })); await Promise.resolve() })
    expect(screen.getByRole<HTMLOptionElement>('option', { name: 'sherpa-onnx ASR' }).disabled).toBe(false)
    expect(screen.getByRole<HTMLOptionElement>('option', { name: 'Faster Whisper' }).disabled).toBe(true)
  })

  it.each([undefined, []])('uses catalog fallback only when custom engines is absent (%j)', async (custom_engines) => {
    stubApi((url) => url === '/api/models'
      ? jsonResponse(200, { models: [model({ model_id: 'tiny' })], disk: DISK, ...(custom_engines === undefined ? {} : { custom_engines }) })
      : undefined, tasks([]))
    render(<ModelManager />)
    await screen.findByRole('heading', { name: 'Transcripción' })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Añadir modelo propio' })); await Promise.resolve() })
    expect(screen.getByRole<HTMLOptionElement>('option', { name: 'Faster Whisper' }).disabled).toBe(custom_engines !== undefined)
  })

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

    expect(
      await screen.findByRole('heading', { level: 2, name: 'Transcripción' }),
    ).toBeDefined()
    expect(
      screen
        .getAllByRole('columnheader')
        // Quita el texto accesible de ordenación que Carbon antepone al título.
        .map((header) => header.textContent?.replace(/^Ordenar .* ascendente/, '')),
    ).toEqual(['Modelo', 'Estado', 'Perfil', 'Tamaño', 'Licencia', 'Acciones'])
    const names = dataRows().map((row) => within(row).getAllByRole('cell')[0]?.textContent)
    expect(names[0]).toMatch(/^Faster Whisper turboRecomendado/)
    expect(names[1]).toBe('Faster Whisper large-v3')
    expect(names[2]).toBe('Faster Whisper tiny')
    expect(screen.getByRole('button', { name: 'Recomendado' })).toBeDefined()
    expect(screen.getByText('Calidad')).toBeDefined()
    expect(screen.getAllByRole('button', { name: /descargar \(1,6\sGB\)/i })).toHaveLength(2)
    expect(screen.getByText('Instalado')).toBeDefined()
    expect(screen.getByText(/espacio libre/i).textContent).toMatch(/50\sGB/)
    expect(screen.getAllByText('MIT').length).toBeGreaterThan(0)
  })

  it('ofrece usar la copia local sin descargar y avisa al terminar', async () => {
    let installBody: unknown
    let listed = 0
    const onModelsChanged = vi.fn()
    stubApi(
      (url, init) => {
        if (url === '/api/models/faster-whisper%3Atiny/install' && init?.method === 'POST') {
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

    expect(await screen.findByText('Ya está en este equipo')).toBeDefined()
    expect(
      screen.getByText(/reutiliza archivos de otra app de este equipo sin descargar nada/i),
    ).toBeDefined()
    // La app nunca nombra a la aplicación de origen: el origen solo viaja en la API.
    expect(document.body.textContent).not.toMatch(/buzz/i)
    fireEvent.click(screen.getByRole('button', { name: /usar copia local/i }))

    await waitFor(() => {
      expect(onModelsChanged).toHaveBeenCalledTimes(1)
    })
    expect(installBody).toEqual({ method: 'import', origin: 'buzz', confirm: true })
  })

  it('no ofrece usar una copia local si el backend no detecta ninguna', async () => {
    stubApi(models([model({ model_id: 'tiny' })]), tasks([]))
    render(<ModelManager />)
    await screen.findByRole('button', { name: /descargar/i })
    expect(screen.queryByRole('button', { name: /usar copia local/i })).toBeNull()
    expect(screen.queryByText('Ya está en este equipo')).toBeNull()
    expect(screen.getByText('No instalado')).toBeDefined()
  })

  it('pide confirmación con tamaño y origen antes de descargar', async () => {
    let installBody: unknown
    const fetchMock = stubApi(
      (url, init) => {
        if (url === '/api/models/faster-whisper%3Aturbo/install' && init?.method === 'POST') {
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
    expect(bar.getAttribute('aria-valuenow')).toBe('400000000')

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
        url === '/api/models/faster-whisper%3Aturbo/install' && init?.method === 'POST'
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
        if (url.startsWith('/api/models/faster-whisper%3Atiny') && init?.method === 'DELETE') {
          deleteUrl = url
          deleted = true
          return jsonResponse(200, {
            key: 'faster-whisper:tiny',
            model_id: 'tiny',
            freed_bytes: 77_003_619,
          })
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
    expect(deleteUrl).toBe(
      '/api/models/faster-whisper%3Atiny?confirm=faster-whisper%3Atiny',
    )
    expect(await screen.findByRole('button', { name: /descargar/i })).toBeDefined()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('explica model_in_use dentro del diálogo de borrado', async () => {
    stubApi(
      (url, init) =>
        url.startsWith('/api/models/faster-whisper%3Atiny') && init?.method === 'DELETE'
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

    expect(await within(dialog).findByText(/en uso por una transcripción/i)).toBeDefined()
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
    expect(await screen.findByRole('table')).toBeDefined()
  })

  it('no ofrece acciones de instalación sobre un modelo con tarea activa', async () => {
    stubApi(models([model({ model_id: 'turbo' })]), tasks([task()]))
    render(<ModelManager />)
    await screen.findByRole('status')
    expect(screen.queryByRole('button', { name: /descargar/i })).toBeNull()
  })

  it('distingue "small" de faster-whisper y de whisper.cpp por su clave', async () => {
    let installUrl = ''
    stubApi(
      (url, init) => {
        if (url.endsWith('/install') && init?.method === 'POST') {
          installUrl = url
          return jsonResponse(
            202,
            task({ key: 'whisper-cpp:small', model_id: 'small', state: 'queued' }),
          )
        }
        return undefined
      },
      models([
        model({
          key: 'whisper-cpp:small',
          provider_id: 'whisper-cpp',
          requires: 'whisper-cli',
          display_name: 'whisper.cpp Small',
          model_id: 'small',
        }),
        model({ model_id: 'small', display_name: 'Faster Whisper Small' }),
      ]),
      tasks([]),
    )

    render(<ModelManager />)
    await screen.findByRole('table')
    const rows = dataRows()
    expect(rows.map((row) => within(row).getAllByRole('cell')[0]?.textContent)).toEqual([
      'Faster Whisper Small',
      'whisper.cpp SmallRequiere whisper-cli',
    ])

    const [, cpp] = rows
    fireEvent.click(within(cpp as HTMLElement).getByRole('button', { name: /descargar/i }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Descargar' }))

    await waitFor(() => {
      expect(installUrl).toBe('/api/models/whisper-cpp%3Asmall/install')
    })
  })

  it('la tarea de whisper.cpp solo afecta a la fila de su clave', async () => {
    stubApi(
      models([
        model({
          key: 'whisper-cpp:small',
          provider_id: 'whisper-cpp',
          requires: 'whisper-cli',
          display_name: 'whisper.cpp Small',
          model_id: 'small',
        }),
        model({ model_id: 'small', display_name: 'Faster Whisper Small' }),
      ]),
      tasks([task({ key: 'whisper-cpp:small', model_id: 'small' })]),
    )

    render(<ModelManager />)
    await screen.findByRole('status')

    const [faster, cpp] = dataRows() as [HTMLElement, HTMLElement]
    expect(within(faster).getByRole('button', { name: /descargar/i })).toBeDefined()
    expect(within(cpp).getByRole('status')).toBeDefined()
  })

  describe('hablantes', () => {
    const speakers = (overrides: Partial<ModelView> = {}) =>
      model({
        key: 'diarization:sherpa-default',
        provider_id: 'diarization',
        kind: 'diarization',
        requires: 'diarization',
        model_id: 'sherpa-default',
        display_name: 'Separación de hablantes (sherpa-onnx)',
        source: null,
        revision: null,
        profile: null,
        license: 'MIT (pyannote segmentation) · CC-BY-4.0 (WeSpeaker, VoxCeleb-trained)',
        size_bytes: 33_488_994,
        ...overrides,
      })

    it('muestra la separación de hablantes en su propia sección y la instala', async () => {
      let installUrl = ''
      stubApi(
        (url, init) => {
          if (url.endsWith('/install') && init?.method === 'POST') {
            installUrl = url
            return jsonResponse(
              202,
              task({ key: 'diarization:sherpa-default', model_id: 'sherpa-default', state: 'queued' }),
            )
          }
          return undefined
        },
        models([model({ model_id: 'turbo' }), speakers()]),
        tasks([]),
      )

      render(<ModelManager />)

      const section = (
        await screen.findByRole('heading', { level: 2, name: 'Hablantes' })
      ).closest('section') as HTMLElement
      expect(dataRows(section)).toHaveLength(1)
      expect(section.textContent).toMatch(/CC-BY-4\.0/)
      // Sin perfil: la columna muestra un guion, no «Rápido» ni «Calidad».
      expect(section.textContent).not.toMatch(/Rápido|Calidad/)
      fireEvent.click(within(section).getByRole('button', { name: /descargar \(33\sMB\)/i }))
      const dialog = await screen.findByRole('dialog')
      expect(dialog.textContent).toMatch(/GitHub/)
      fireEvent.click(within(dialog).getByRole('button', { name: 'Descargar' }))

      await waitFor(() => {
        expect(installUrl).toBe('/api/models/diarization%3Asherpa-default/install')
      })
    })

    it('sin el extra diarization explica el requisito y no ofrece instalar', async () => {
      stubApi(models([speakers({ runtime_available: false })]), tasks([]))

      render(<ModelManager />)

      await screen.findByRole('table')
      const [row] = dataRows() as [HTMLElement]
      expect(row.textContent).toMatch(/requiere el extra «diarization»/i)
      expect(within(row).queryByRole('button', { name: /descargar|usar copia|eliminar/i })).toBeNull()
    })

    it('instalado permite eliminarlo con confirmación por clave', async () => {
      let deleteUrl = ''
      stubApi(
        (url, init) => {
          if (init?.method === 'DELETE') {
            deleteUrl = url
            return jsonResponse(200, {
              key: 'diarization:sherpa-default',
              model_id: 'sherpa-default',
              freed_bytes: 1,
            })
          }
          return undefined
        },
        models([speakers({ installed: true, disk_bytes: 33_000_000 })]),
        tasks([]),
      )

      render(<ModelManager />)
      fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }))
      const dialog = await screen.findByRole('dialog')
      fireEvent.change(within(dialog).getByLabelText(/escribe/i), {
        target: { value: 'sherpa-default' },
      })
      fireEvent.click(within(dialog).getByRole('button', { name: 'Eliminar' }))

      await waitFor(() => {
        expect(deleteUrl).toBe(
          '/api/models/diarization%3Asherpa-default?confirm=diarization%3Asherpa-default',
        )
      })
    })
  })

  describe('tamaños y estados', () => {
    it('muestra los bytes reales en disco y oculta un 0 B engañoso', async () => {
      stubApi(
        models([
          model({ model_id: 'tiny', size_bytes: 77_003_619, installed: true, disk_bytes: 77_010_000 }),
          model({ model_id: 'small', size_bytes: 486_212_372, installed: true, disk_bytes: 0 }),
        ]),
        tasks([]),
      )
      render(<ModelManager />)
      await screen.findByRole('table')

      expect(screen.getByText(/En disco: 77\sMB/)).toBeDefined()
      expect(screen.queryByText(/En disco: 0\sB/)).toBeNull()
    })

    it('las etiquetas de estado son rectangulares y explican su significado', async () => {
      stubApi(
        models([
          model({ model_id: 'tiny', installed: true, disk_bytes: 1_000_000 }),
          model({ model_id: 'small', external: [{ origin: 'buzz' }] }),
          model({ model_id: 'base' }),
        ]),
        tasks([]),
      )
      render(<ModelManager />)
      await screen.findByRole('table')

      for (const label of ['Instalado', 'Ya está en este equipo', 'No instalado']) {
        expect(screen.getByRole('button', { name: label })).toBeDefined()
      }
      expect(document.body.textContent).not.toMatch(/buzz/i)
    })

    it('en inglés traduce encabezados, estados y acciones', async () => {
      setLang('en')
      stubApi(models([model({ model_id: 'tiny' })]), tasks([]))
      render(<ModelManager />)

      expect(await screen.findByRole('heading', { level: 2, name: 'Transcription' })).toBeDefined()
      expect(screen.getByRole('columnheader', { name: /Status/ })).toBeDefined()
      expect(screen.getByRole('button', { name: 'Not installed' })).toBeDefined()
      expect(screen.getByRole('button', { name: /Download \(1.6\sGB\)/ })).toBeDefined()
    })
  })
  describe('secciones por capacidad y licencia antes de descargar', () => {
    beforeEach(() => {
      setLang('es')
    })

    const speakerModel = () =>
      model({
        key: 'diarization:sherpa-default',
        provider_id: 'diarization',
        kind: 'diarization',
        requires: 'diarization',
        model_id: 'sherpa-default',
        display_name: 'Separación de hablantes (sherpa-onnx)',
        source: null,
        revision: null,
        profile: null,
        capabilities: ['cpu', 'diarization'],
        license: 'MIT (pyannote segmentation) · CC-BY-4.0 (WeSpeaker, VoxCeleb-trained)',
        size_bytes: 33_488_994,
      })
    const asr = (id: string) => model({ model_id: id, capabilities: ['transcription', 'cpu'] })
    const voiceModel = () =>
      model({
        key: 'sherpa-tts:kitten',
        provider_id: 'sherpa-tts',
        kind: 'tts',
        model_id: 'kitten',
        display_name: 'Kitten TTS',
        source: 'org/kitten-tts',
        revision: '0123456789abcdef0123456789abcdef01234567',
        profile: null,
        capabilities: ['cpu', 'synthesis'],
        license: 'Apache-2.0',
        size_bytes: 25_000_000,
      })

    it('agrupa por capacidad principal y no muestra secciones vacías', async () => {
      stubApi(models([speakerModel(), asr('turbo')]), tasks([]))

      render(<ModelManager />)

      await screen.findByRole('heading', { level: 2, name: 'Transcripción' })
      const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
      expect(headings).toEqual(['Transcripción', 'Hablantes'])
      expect(screen.queryByRole('heading', { name: 'Síntesis de voz' })).toBeNull()
      const transcription = screen.getByRole('region', { name: 'Transcripción' })
      const speakers = screen.getByRole('region', { name: 'Hablantes' })
      expect(within(transcription).getAllByRole('row')).toHaveLength(2)
      expect(within(speakers).getAllByRole('row')).toHaveLength(2)
    })

    it('muestra la sección de síntesis cuando hay modelos con synthesis', async () => {
      stubApi(models([voiceModel(), asr('turbo')]), tasks([]))

      render(<ModelManager />)

      const section = await screen.findByRole('region', { name: 'Síntesis de voz' })
      expect(within(section).getAllByRole('row')).toHaveLength(2)
      expect(within(section).getByText('Kitten TTS')).toBeDefined()
      expect(
        within(screen.getByRole('region', { name: 'Transcripción' })).queryByText('Kitten TTS'),
      ).toBeNull()
      expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
        'Transcripción',
        'Síntesis de voz',
      ])
    })

    it('lista las capacidades legibles en cada fila, sin repetir la principal', async () => {
      stubApi(
        models([
          model({
            model_id: 'turbo',
            capabilities: [
              'gpu',
              'word_timestamps',
              'transcription',
              'translation',
              'language_detection',
              'cpu',
            ],
          }),
        ]),
        tasks([]),
      )

      render(<ModelManager />)

      const [row] = (await screen.findAllByRole('row')).slice(1) as [HTMLElement]
      expect(row.textContent).toContain(
        'Capacidades: Traducción al inglés · Detección de idioma · Tiempos por palabra · CPU · GPU',
      )
      expect(row.textContent).not.toMatch(/Capacidades: Transcripción/)
    })

    it('un modelo sin capacidades (respuesta antigua) sigue en Transcripción', async () => {
      stubApi(models([model({ model_id: 'tiny' }), model({ model_id: 'base' })]), tasks([]))

      render(<ModelManager />)

      const section = await screen.findByRole('region', { name: 'Transcripción' })
      expect(within(section).getAllByRole('row')).toHaveLength(3)
      expect(section.textContent).not.toMatch(/Capacidades/)
    })

    it('el diálogo de descarga muestra licencia, fuente corta y capacidades antes de instalar', async () => {
      const fetchMock = stubApi(
        models([
          model({
            model_id: 'turbo',
            license: 'MIT',
            revision: 'd90ca5fe260221311c53c58e660288d3deb8d356',
            capabilities: ['transcription', 'translation', 'cpu', 'gpu'],
          }),
        ]),
        tasks([]),
      )

      render(<ModelManager />)
      fireEvent.click(await screen.findByRole('button', { name: /descargar \(1,6\sGB\)/i }))

      const dialog = await screen.findByRole('dialog', { name: /descargar faster whisper turbo/i })
      const facts = within(dialog)
      expect(facts.getByText('Licencia').nextElementSibling?.textContent).toBe('MIT')
      expect(facts.getByText('Fuente').nextElementSibling?.textContent).toBe(
        'Systran/faster-whisper-turbo · revisión d90ca5f',
      )
      expect(facts.getByText('Capacidades').nextElementSibling?.textContent).toBe(
        'Transcripción · Traducción al inglés · CPU · GPU',
      )
      expect(dialog.textContent).toMatch(/1,6\sGB/)
      expect(dialog.textContent).toMatch(/Léela antes de descargarlo/)
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
    })

    it('para hablantes explica la fuente verificada y no inventa revisión', async () => {
      stubApi(models([speakerModel()]), tasks([]))

      render(<ModelManager />)
      fireEvent.click(await screen.findByRole('button', { name: /descargar \(33\sMB\)/i }))

      const dialog = await screen.findByRole('dialog')
      expect(within(dialog).getByText('Licencia').nextElementSibling?.textContent).toMatch(
        /CC-BY-4\.0/,
      )
      expect(within(dialog).getByText('Fuente').nextElementSibling?.textContent).toMatch(
        /SHA-256/,
      )
      expect(dialog.textContent).not.toMatch(/revisión/)
    })

    it('traduce el requisito «tts» en vez de mostrar el texto crudo', async () => {
      const needsEngine = () =>
        model({
          ...voiceModel(),
          requires: 'tts',
          runtime_available: false,
        })
      stubApi(models([needsEngine()]), tasks([]))

      const view = render(<ModelManager />)

      const section = await screen.findByRole('region', { name: 'Síntesis de voz' })
      expect(section.textContent).toMatch(/Requiere el motor de voz \(sherpa-onnx\)/)
      expect(section.textContent).not.toMatch(/Requiere tts/)
      view.unmount()

      setLang('en')
      stubApi(models([needsEngine()]), tasks([]))
      render(<ModelManager />)
      const english = await screen.findByRole('region', { name: 'Speech synthesis' })
      expect(english.textContent).toMatch(/Requires the speech engine \(sherpa-onnx\)/)
    })

    it('en inglés traduce secciones, capacidades y datos del diálogo', async () => {
      setLang('en')
      stubApi(models([voiceModel()]), tasks([]))

      render(<ModelManager />)

      expect(await screen.findByRole('heading', { level: 2, name: 'Speech synthesis' })).toBeDefined()
      fireEvent.click(screen.getByRole('button', { name: /Download/ }))
      const dialog = await screen.findByRole('dialog')
      expect(within(dialog).getByText('License').nextElementSibling?.textContent).toBe('Apache-2.0')
      expect(within(dialog).getByText('Capabilities').nextElementSibling?.textContent).toBe(
        'Speech synthesis · CPU',
      )
      expect(dialog.textContent).toMatch(/revision 0123456/)
    })
  })
})
