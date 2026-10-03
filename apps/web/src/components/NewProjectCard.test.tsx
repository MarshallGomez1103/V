import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { NewProjectCard } from './NewProjectCard'

class FakeXMLHttpRequest {
  static instances: FakeXMLHttpRequest[] = []

  method = ''
  url = ''
  headers: Record<string, string> = {}
  body: unknown = undefined
  status = 0
  responseText = ''
  upload: { onprogress: ((event: ProgressEvent) => void) | null } = {
    onprogress: null,
  }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  onabort: (() => void) | null = null

  open(method: string, url: string) {
    this.method = method
    this.url = url
  }

  setRequestHeader(key: string, value: string) {
    this.headers[key] = value
  }

  send(body: unknown) {
    this.body = body
    FakeXMLHttpRequest.instances.push(this)
  }

  abort() {
    this.onabort?.()
  }

  progress(loaded: number, total: number) {
    this.upload.onprogress?.({
      lengthComputable: true,
      loaded,
      total,
    } as ProgressEvent)
  }

  respond(status: number, body: unknown) {
    this.status = status
    this.responseText = JSON.stringify(body)
    this.onload?.()
  }
}

const project = {
  id: 'p-1',
  name: 'Clase de cálculo',
  created_at: '2026-09-21T10:00:00Z',
}

const media = {
  media_asset_id: 'm-1',
  project_id: 'p-1',
  filename: 'clase.mp3',
  media_type: 'audio',
  duration_ms: 125_000,
  sha256: 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789',
}

function makeFile(name = 'clase.mp3') {
  return new File(['hola'], name, { type: 'audio/mpeg' })
}

function stubCreateProject() {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 201,
    json: () => Promise.resolve(project),
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function waitForUpload(): Promise<FakeXMLHttpRequest> {
  await vi.waitFor(() => {
    expect(FakeXMLHttpRequest.instances.length).toBeGreaterThan(0)
  })
  const request = FakeXMLHttpRequest.instances.at(-1)
  if (!request) {
    throw new Error('sin petición')
  }
  return request
}

function selectFile(file: File) {
  fireEvent.change(screen.getByLabelText(/suelta aquí tu audio o video/i), {
    target: { files: [file] },
  })
}

function setName(value: string) {
  fireEvent.change(screen.getByLabelText(/nombre del proyecto/i), {
    target: { value },
  })
}

beforeEach(() => {
  FakeXMLHttpRequest.instances = []
  vi.stubGlobal('XMLHttpRequest', FakeXMLHttpRequest)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('NewProjectCard', () => {
  it('propone un nombre por defecto y bloquea el envío sin archivo', () => {
    stubCreateProject()
    render(<NewProjectCard onImported={vi.fn()} />)

    const nameInput = screen.getByLabelText<HTMLInputElement>(/nombre del proyecto/i)
    expect(nameInput.value).toMatch(/^Grabación /)
    expect(
      screen.getByRole('button', { name: /crear proyecto e importar/i }),
    ).toHaveProperty('disabled', true)
  })

  it('crea el proyecto, sube el archivo con progreso y avisa con onImported', async () => {
    const fetchMock = stubCreateProject()
    const onImported = vi.fn()
    render(<NewProjectCard onImported={onImported} />)

    setName('  Clase de cálculo  ')
    const file = makeFile()
    selectFile(file)

    expect(screen.getByText('clase.mp3')).toBeDefined()
    expect(screen.getByText(/archivo listo · 4 B/i)).toBeDefined()

    fireEvent.click(screen.getByRole('button', { name: /crear proyecto e importar/i }))

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/projects',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ name: 'Clase de cálculo' }),
      }),
    )

    const request = await waitForUpload()
    expect(request.method).toBe('POST')
    expect(request.url).toBe('/api/projects/p-1/media')
    expect(request.headers['Content-Type']).toBe('application/octet-stream')
    expect(request.headers['X-Voz-Filename']).toBe('clase.mp3')
    expect(request.body).toBe(file)

    act(() => {
      request.progress(50, 100)
    })
    expect(screen.getByText('Subiendo 50 %')).toBeDefined()
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('50')

    await act(async () => {
      request.respond(201, media)
      await Promise.resolve()
    })

    expect(onImported).toHaveBeenCalledWith({ project, media })
    expect(await screen.findByText(/importación completa/i)).toBeDefined()
    expect(screen.getByText('02:05')).toBeDefined()
    expect(screen.getByText('Audio')).toBeDefined()
    expect(screen.getByText('abcdef01')).toBeDefined()
    expect(screen.queryByText(media.sha256)).toBeNull()
  })

  it('selecciona el archivo soltado en la zona y avisa si eran varios', () => {
    stubCreateProject()
    render(<NewProjectCard onImported={vi.fn()} />)

    const zone = screen.getByRole('button', { name: /suelta aquí tu audio o video/i })

    fireEvent.dragOver(zone, { dataTransfer: { files: [] } })
    expect(zone.className).toContain('drag-over')

    fireEvent.drop(zone, {
      dataTransfer: { files: [makeFile('primero.wav'), makeFile('segundo.wav')] },
    })

    expect(zone.className).not.toContain('drag-over')
    expect(screen.getByText('primero.wav')).toBeDefined()
    expect(screen.getByText(/solo se importa un archivo a la vez/i)).toBeDefined()
    expect(
      screen.getByRole('button', { name: /crear proyecto e importar/i }),
    ).toHaveProperty('disabled', false)
  })

  it('traduce el 415 y reintentar vuelve a subir sin crear otro proyecto', async () => {
    const fetchMock = stubCreateProject()
    const onImported = vi.fn()
    render(<NewProjectCard onImported={onImported} />)

    selectFile(makeFile())
    fireEvent.click(screen.getByRole('button', { name: /crear proyecto e importar/i }))

    const first = await waitForUpload()
    await act(async () => {
      first.respond(415, {
        detail: { code: 'media_unsupported', message: 'raw ffmpeg stderr' },
      })
      await Promise.resolve()
    })

    expect(
      await screen.findByText('FFmpeg no reconoce este archivo como audio o video.'),
    ).toBeDefined()
    expect(screen.queryByText(/raw ffmpeg stderr/)).toBeNull()
    expect(screen.getByText('clase.mp3')).toBeDefined()
    expect(onImported).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: /reintentar/i }))

    await vi.waitFor(() => {
      expect(FakeXMLHttpRequest.instances).toHaveLength(2)
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)

    const second = FakeXMLHttpRequest.instances[1]
    if (!second) {
      throw new Error('sin reintento')
    }
    expect(second.headers['X-Voz-Filename']).toBe('clase.mp3')

    await act(async () => {
      second.respond(201, media)
      await Promise.resolve()
    })

    expect(onImported).toHaveBeenCalledTimes(1)
  })

  it('bloquea el envío cuando el nombre queda vacío', () => {
    const fetchMock = stubCreateProject()
    render(<NewProjectCard onImported={vi.fn()} />)

    selectFile(makeFile())
    setName('   ')

    const submit = screen.getByRole('button', { name: /crear proyecto e importar/i })
    expect(submit).toHaveProperty('disabled', true)

    fireEvent.submit(submit.closest('form') as HTMLFormElement)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(FakeXMLHttpRequest.instances).toHaveLength(0)
  })

  it('muestra el error del proyecto cuando la API rechaza el nombre', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: () =>
          Promise.resolve({
            detail: { code: 'project_name_invalid', message: 'bad' },
          }),
      }),
    )
    render(<NewProjectCard onImported={vi.fn()} />)

    selectFile(makeFile())
    fireEvent.click(screen.getByRole('button', { name: /crear proyecto e importar/i }))

    expect(
      await screen.findByText('El nombre del proyecto no es válido.'),
    ).toBeDefined()
    expect(FakeXMLHttpRequest.instances).toHaveLength(0)
  })
})
