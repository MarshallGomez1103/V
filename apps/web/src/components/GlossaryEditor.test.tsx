import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { GlossaryEditor } from './GlossaryEditor'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function glossary(terms: string[]) {
  return { terms, max_terms: 3, max_term_length: 10, applies_to: ['faster-whisper', 'cloud-x'] }
}

function response(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response
}

describe('GlossaryEditor', () => {
  it('carga los términos, uno por línea, y dice qué motores lo usan', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(response(200, glossary(['VOZ', 'ADN']))),
    )
    render(<GlossaryEditor projectId="p1" />)

    const box = await screen.findByLabelText('Glosario del proyecto')
    expect(box).toHaveProperty('value', 'VOZ\nADN')
    expect(screen.getByText(/Lo usan: faster-whisper, cloud-x/)).toBeTruthy()
    expect(screen.getByText(/no cambia el texto transcrito/)).toBeTruthy()
  })

  it('guarda los términos normalizados con PUT y muestra la confirmación', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(response(200, glossary([])))
      .mockResolvedValueOnce(response(200, glossary(['VOZ', 'ADN'])))
    vi.stubGlobal('fetch', fetchMock)
    render(<GlossaryEditor projectId="p1" />)

    fireEvent.change(await screen.findByLabelText('Glosario del proyecto'), {
      target: { value: ' VOZ \n\nADN\nVOZ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar glosario' }))

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain('2 términos')
    })
    const init = fetchMock.mock.calls[1]?.[1]
    expect(init?.method).toBe('PUT')
    expect(init?.body).toBe(JSON.stringify({ terms: ['VOZ', 'ADN'] }))
  })

  it('bloquea guardar si hay demasiados términos o alguno es muy largo', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(response(200, glossary([]))),
    )
    render(<GlossaryEditor projectId="p1" />)
    const box = await screen.findByLabelText('Glosario del proyecto')
    const save = screen.getByRole('button', { name: 'Guardar glosario' })

    fireEvent.change(box, { target: { value: 'a\nb\nc\nd' } })
    expect(save).toHaveProperty('disabled', true)
    expect(screen.getByText(/demasiados/)).toBeTruthy()

    fireEvent.change(box, { target: { value: 'x'.repeat(11) } })
    expect(save).toHaveProperty('disabled', true)
    expect(screen.getByText(/supera/)).toBeTruthy()

    fireEvent.change(box, { target: { value: 'ok' } })
    expect(save).toHaveProperty('disabled', false)
  })

  it('muestra el error del servidor al guardar y conserva lo escrito', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn<typeof fetch>()
        .mockResolvedValueOnce(response(200, glossary([])))
        .mockResolvedValueOnce(
          response(422, { detail: { code: 'glossary_invalid', message: 'x' } }),
        ),
    )
    render(<GlossaryEditor projectId="p1" />)

    const box = await screen.findByLabelText('Glosario del proyecto')
    fireEvent.change(box, { target: { value: 'VOZ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar glosario' }))

    expect(await screen.findByText(/no es válido/)).toBeTruthy()
    expect(box).toHaveProperty('value', 'VOZ')
  })

  it('disabled bloquea el editor', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(response(200, glossary([]))),
    )
    render(<GlossaryEditor projectId="p1" disabled />)

    expect(await screen.findByLabelText('Glosario del proyecto')).toHaveProperty(
      'disabled',
      true,
    )
  })
})
