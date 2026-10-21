import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setLang } from '../i18n/i18n'
import { SpeakWorkspace } from './SpeakWorkspace'

vi.mock('./SpeakHistory', () => ({ SpeakHistory: () => null }))

beforeEach(() => {
  setLang('es')
  window.localStorage.clear()
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

const MODEL = {
  provider_id: 'sherpa-onnx',
  model_id: 'piper-es',
  display_name: 'Piper es_MX',
  runtime_ready: true,
  languages: ['es'],
  voices: [
    { id: '0', name: 'Ald', languages: ['es'] },
    { id: '1', name: 'Claude', languages: ['es'] },
  ],
}

function options(overrides: Record<string, unknown> = {}) {
  return {
    providers: [{ provider_id: 'sherpa-onnx', display_name: 'sherpa-onnx', locality: 'local' }],
    models: [MODEL],
    max_chars: 100,
    speed: { min: 0.5, max: 2 },
    ...overrides,
  }
}

function stubFetch(...responses: (Response | Error)[]) {
  const fetchMock = vi.fn<typeof fetch>()
  for (const response of responses) {
    if (response instanceof Error) {
      fetchMock.mockRejectedValueOnce(response)
    } else {
      fetchMock.mockResolvedValueOnce(response)
    }
  }
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const model = () => screen.getByLabelText<HTMLSelectElement>('Modelo')
const voice = () => screen.getByLabelText<HTMLSelectElement>('Voz', { selector: 'select' })
const area = () => screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Texto a convertir en voz' })

describe('SpeakWorkspace', () => {
  it('un modelo cloud exige confirmación antes de generar o escuchar muestra', async () => {
    stubFetch(jsonResponse(200, options({
      providers: [{ provider_id: MODEL.provider_id, display_name: 'Remote', locality: 'cloud' }],
    })))
    render(<SpeakWorkspace onOpenModels={() => undefined} />)
    await screen.findByRole('textbox', { name: 'Texto a convertir en voz' })
    fireEvent.change(area(), { target: { value: 'Hola' } })
    const generate = screen.getByRole<HTMLButtonElement>('button', { name: 'Generar audio' })
    const sample = screen.getByRole<HTMLButtonElement>('button', { name: 'Escuchar muestra' })
    expect(generate.disabled).toBe(true)
    expect(sample.disabled).toBe(true)
    fireEvent.click(screen.getByRole('checkbox'))
    expect(generate.disabled).toBe(false)
    expect(sample.disabled).toBe(false)
    fireEvent.change(voice(), { target: { value: '1' } })
    expect(generate.disabled).toBe(true)
    expect(sample.disabled).toBe(true)
  })

  it('muestra «cargando» mientras llegan las opciones', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => undefined)))

    render(<SpeakWorkspace onOpenModels={() => undefined} />)

    expect(screen.getByText('Buscando las voces instaladas')).toBeDefined()
  })

  it('sin modelos invita a ir a Modelos', async () => {
    stubFetch(jsonResponse(200, options({ providers: [], models: [] })))
    const onOpenModels = vi.fn()

    render(<SpeakWorkspace onOpenModels={onOpenModels} />)

    await screen.findByRole('heading', { name: 'No hay voces instaladas' })
    expect(screen.queryByRole('textbox')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Ir a Modelos' }))
    expect(onOpenModels).toHaveBeenCalledTimes(1)
  })

  it('un error de la API se muestra con Reintentar, que vuelve a pedir las opciones', async () => {
    const fetchMock = stubFetch(
      jsonResponse(500, { detail: { code: 'weird_failure', message: 'x' } }),
      jsonResponse(200, options()),
    )

    render(<SpeakWorkspace onOpenModels={() => undefined} />)

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toMatch(/No se pudieron cargar las voces/)
    expect(alert.textContent).toMatch(/weird_failure/)
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))

    await screen.findByRole('textbox', { name: 'Texto a convertir en voz' })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(screen.queryByText(/No se pudieron cargar las voces/)).toBeNull()
  })

  it('una respuesta inválida cuenta como error, no como lista vacía', async () => {
    stubFetch(jsonResponse(200, { models: 'no' }))

    render(<SpeakWorkspace onOpenModels={() => undefined} />)

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toMatch(/V no entiende/)
  })

  it('listo: editor, contador, resumen de voces y selectores reales', async () => {
    stubFetch(jsonResponse(200, options()))

    render(<SpeakWorkspace onOpenModels={() => undefined} />)

    await screen.findByRole('textbox', { name: 'Texto a convertir en voz' })
    expect(screen.getByTestId('speak-counter').textContent).toBe('0 de 100 caracteres · 0 palabras')
    expect(screen.getByText('Instalado: 1 modelo · 2 voces')).toBeDefined()
    expect(screen.queryByTestId('speak-selectors-placeholder')).toBeNull()
    expect(model().disabled).toBe(false)
    expect(voice().disabled).toBe(false)
  })

  it('el resumen de modelos y voces concuerda en singular y plural, en inglés y español', async () => {
    const one = { ...MODEL, voices: [MODEL.voices[0]] }
    const two = { ...MODEL, model_id: 'piper-en', voices: [MODEL.voices[0]] }
    setLang('en')
    stubFetch(jsonResponse(200, options({ models: [one] })))
    const first = render(<SpeakWorkspace onOpenModels={() => undefined} />)
    expect(await screen.findByText('Installed: 1 model · 1 voice')).toBeDefined()
    first.unmount()

    stubFetch(jsonResponse(200, options({ models: [one, two] })))
    const second = render(<SpeakWorkspace onOpenModels={() => undefined} />)
    expect(await screen.findByText('Installed: 2 models · 2 voices')).toBeDefined()
    second.unmount()

    setLang('es')
    stubFetch(jsonResponse(200, options({ models: [one, two] })))
    render(<SpeakWorkspace onOpenModels={() => undefined} />)
    expect(await screen.findByText('Instalado: 2 modelos · 2 voces')).toBeDefined()
  })

  it('cuenta caracteres y palabras al escribir y Borrar vacía el texto', async () => {
    stubFetch(jsonResponse(200, options()))
    render(<SpeakWorkspace onOpenModels={() => undefined} />)
    await screen.findByRole('textbox', { name: 'Texto a convertir en voz' })

    fireEvent.change(area(), { target: { value: 'Hola mundo\ncómo estás' } })
    expect(screen.getByTestId('speak-counter').textContent).toBe('21 de 100 caracteres · 4 palabras')

    fireEvent.change(area(), { target: { value: 'Hola' } })
    expect(screen.getByTestId('speak-counter').textContent).toBe('4 de 100 caracteres · 1 palabra')

    fireEvent.click(screen.getByRole('button', { name: 'Borrar el texto' }))
    expect(area().value).toBe('')
  })

  it('avisa al acercarse al límite y bloquea (inválido) al pasarse', async () => {
    stubFetch(jsonResponse(200, options()))
    render(<SpeakWorkspace onOpenModels={() => undefined} />)
    await screen.findByRole('textbox', { name: 'Texto a convertir en voz' })

    fireEvent.change(area(), { target: { value: 'a'.repeat(95) } })
    expect(screen.getByText('Te acercas al límite: quedan 5 caracteres.')).toBeDefined()
    expect(area().getAttribute('aria-invalid')).not.toBe('true')

    fireEvent.change(area(), { target: { value: 'a'.repeat(104) } })
    expect(
      screen.getByText('El texto supera el límite por 4 caracteres. Acórtalo para poder generar el audio.'),
    ).toBeDefined()
    expect(area().getAttribute('aria-invalid')).toBe('true')

    fireEvent.change(area(), { target: { value: 'a'.repeat(50) } })
    expect(area().getAttribute('aria-invalid')).not.toBe('true')
    expect(screen.queryByText(/Te acercas al límite/)).toBeNull()
  })

  it('conserva el texto al refrescar las opciones por un cambio en Modelos', async () => {
    const fetchMock = stubFetch(jsonResponse(200, options()), jsonResponse(200, options({ max_chars: 200 })))
    const view = render(<SpeakWorkspace modelsVersion={0} onOpenModels={() => undefined} />)
    await screen.findByRole('textbox', { name: 'Texto a convertir en voz' })
    fireEvent.change(area(), { target: { value: 'Hola' } })

    view.rerender(<SpeakWorkspace modelsVersion={1} onOpenModels={() => undefined} />)

    await waitFor(() => {
      expect(screen.getByTestId('speak-counter').textContent).toMatch(/de 200 caracteres/)
    })
    expect(area().value).toBe('Hola')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('en inglés traduce todo el esqueleto', async () => {
    setLang('en')
    stubFetch(jsonResponse(200, options()))

    render(<SpeakWorkspace onOpenModels={() => undefined} />)

    const textbox = await screen.findByRole('textbox', { name: 'Text to turn into speech' })
    fireEvent.change(textbox, { target: { value: 'Hello' } })
    expect(screen.getByTestId('speak-counter').textContent).toBe('5 of 100 characters · 1 word')
    expect(screen.getByRole('heading', { name: 'Voice' })).toBeDefined()
    expect(screen.getByRole('button', { name: 'Clear the text' })).toBeDefined()
  })

  it('el estado vacío en inglés', async () => {
    setLang('en')
    stubFetch(jsonResponse(200, options({ models: [] })))

    render(<SpeakWorkspace onOpenModels={() => undefined} />)

    await screen.findByRole('heading', { name: 'No voices installed' })
    expect(screen.getByRole('button', { name: 'Go to Models' })).toBeDefined()
  })
})
