import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setLang } from '../i18n/i18n'
import { SpeakWorkspace } from './SpeakWorkspace'

vi.mock('./SpeakHistory', () => ({ SpeakHistory: () => null }))

class FakeEventSource extends EventTarget {
  readyState = 1
  close() {
    this.readyState = 2
  }
}

beforeEach(() => {
  vi.stubGlobal('EventSource', FakeEventSource)
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

const model = (provider_id: string) => ({
  provider_id,
  model_id: 'voice-model',
  display_name: provider_id,
  runtime_ready: true,
  languages: ['es'],
  voices: [{ id: 'voice', name: 'Voice', languages: ['es'] }],
})

function options(providers: { provider_id: string; locality: string }[]) {
  return {
    providers: providers.map((provider) => ({ ...provider, display_name: provider.provider_id })),
    models: ['sherpa', 'remote'].map(model),
    max_chars: 100,
    speed: { min: 0.5, max: 2 },
  }
}

const CREATED = {
  id: 'syn-1',
  state: 'QUEUED',
  progress: 0,
  chunks_done: 0,
  chunks_total: 1,
  error_code: null,
  created_at: '2026-10-21T10:00:00Z',
  updated_at: '2026-10-21T10:00:00Z',
  provider_id: 'remote',
  model_id: 'voice-model',
  voice_id: 'voice',
  speed: 1,
  text_length: 4,
  text_preview: 'Hola',
  reused: false,
}

/** Responde las opciones y registra los cuerpos de `POST /api/synthesis`. */
function stubApi(opts: unknown, post: Response = jsonResponse(201, CREATED)) {
  const posts: Record<string, unknown>[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      if (url === '/api/synthesis/options') return Promise.resolve(jsonResponse(200, opts))
      if (url === '/api/synthesis' && init?.method === 'POST') {
        posts.push(JSON.parse(typeof init.body === 'string' ? init.body : 'null') as Record<string, unknown>)
        return Promise.resolve(post)
      }
      return new Promise<Response>(() => undefined)
    }),
  )
  return posts
}

const MODEL_LABEL = 'Modelo'
const generate = () => screen.getByRole<HTMLButtonElement>('button', { name: 'Generar audio' })

async function ready(opts: unknown, post?: Response) {
  const posts = stubApi(opts, post)
  render(<SpeakWorkspace onOpenModels={() => undefined} />)
  const area = await screen.findByRole('textbox', { name: 'Texto a convertir en voz' })
  fireEvent.change(area, { target: { value: 'Hola' } })
  return posts
}

describe('SpeakWorkspace: consentimiento cloud', () => {
  it('envía cloud_consent solo tras marcar la casilla de un proveedor cloud', async () => {
    const posts = await ready(options([
      { provider_id: 'sherpa', locality: 'local' },
      { provider_id: 'remote', locality: 'cloud' },
    ]))
    fireEvent.change(screen.getByLabelText(MODEL_LABEL), { target: { value: 'remote:voice-model' } })

    expect(generate().disabled).toBe(true)
    fireEvent.click(screen.getByRole('checkbox'))
    expect(generate().disabled).toBe(false)
    fireEvent.click(generate())

    await waitFor(() => { expect(posts).toHaveLength(1) })
    expect(posts[0]).toMatchObject({ provider_id: 'remote', cloud_consent: true })
  })

  it('la muestra de un proveedor cloud también envía el consentimiento', async () => {
    const posts = await ready(options([
      { provider_id: 'sherpa', locality: 'cloud' },
      { provider_id: 'remote', locality: 'cloud' },
    ]))
    const sample = screen.getByRole<HTMLButtonElement>('button', { name: 'Escuchar muestra' })
    expect(sample.disabled).toBe(true)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(sample)

    await waitFor(() => { expect(posts).toHaveLength(1) })
    expect(posts[0]).toMatchObject({ cloud_consent: true })
  })

  it('un proveedor local no muestra casilla ni envía el campo', async () => {
    const posts = await ready(options([
      { provider_id: 'sherpa', locality: 'local' },
      { provider_id: 'remote', locality: 'cloud' },
    ]))

    expect(screen.queryByRole('checkbox')).toBeNull()
    fireEvent.click(generate())

    await waitFor(() => { expect(posts).toHaveLength(1) })
    expect(posts[0]).not.toHaveProperty('cloud_consent')
  })

  it('cambiar de proveedor desmarca la casilla', async () => {
    await ready(options([
      { provider_id: 'sherpa', locality: 'cloud' },
      { provider_id: 'remote', locality: 'cloud' },
    ]))
    fireEvent.click(screen.getByRole('checkbox'))
    expect(generate().disabled).toBe(false)

    fireEvent.change(screen.getByLabelText(MODEL_LABEL), { target: { value: 'remote:voice-model' } })

    expect(screen.getByRole<HTMLInputElement>('checkbox').checked).toBe(false)
    expect(generate().disabled).toBe(true)
  })

  it.each([
    ['localidad desconocida', [{ provider_id: 'sherpa', locality: 'galaxy' }]],
    ['proveedor ausente del catálogo', []],
  ])('falla cerrado con %s: exige consentimiento y lo envía', async (_name, providers) => {
    const posts = await ready(options(providers))

    expect(generate().disabled).toBe(true)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(generate())

    await waitFor(() => { expect(posts).toHaveLength(1) })
    expect(posts[0]).toMatchObject({ cloud_consent: true })
  })

  it('traduce cloud_consent_required si el servidor lo rechaza', async () => {
    await ready(
      options([{ provider_id: 'sherpa', locality: 'local' }, { provider_id: 'remote', locality: 'local' }]),
      jsonResponse(422, { detail: { code: 'cloud_consent_required', message: 'x' } }),
    )
    fireEvent.click(generate())

    expect(await screen.findByText(/confirma el permiso para enviar el texto a la nube/i)).toBeDefined()
  })
})
