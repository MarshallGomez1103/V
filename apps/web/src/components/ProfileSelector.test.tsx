import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ProfileSelector } from './ProfileSelector'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function payload(recommendation: Record<string, unknown>) {
  return {
    default: 'default',
    profiles: [
      {
        name: 'default',
        label: 'Estándar',
        description: 'Valores por defecto.',
        parameters: {},
      },
      {
        name: 'academic',
        label: 'Académico',
        description: 'Clases largas.',
        parameters: {},
      },
    ],
    recommendation,
  }
}

const MEASURED = {
  language: 'es',
  profile: 'default',
  measured: true,
  evidence: 'WER 1,66 % en docs/benchmarks.md.',
  synthetic: true,
  unmeasured_profiles: ['academic'],
}
const UNMEASURED = {
  language: 'fr',
  profile: null,
  measured: false,
  evidence: 'sin medición para el idioma «fr»',
  synthetic: false,
  unmeasured_profiles: ['default', 'academic'],
}

function stubFetch(body: unknown) {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
  } as unknown as Response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('ProfileSelector', () => {
  it('lista los perfiles, marca el de por defecto y emite el elegido', async () => {
    stubFetch(payload(MEASURED))
    const onChange = vi.fn()
    render(<ProfileSelector value={null} onChange={onChange} language="es" />)

    const standard = await screen.findByLabelText(/Estándar/)
    expect(standard).toHaveProperty('checked', true)
    expect(screen.getByLabelText(/Académico/)).toHaveProperty('checked', false)

    fireEvent.click(screen.getByLabelText(/Académico/))
    expect(onChange).toHaveBeenCalledWith('academic')
  })

  it('muestra la evidencia medida y avisa de que es audio sintético', async () => {
    const fetchMock = stubFetch(payload(MEASURED))
    render(<ProfileSelector value="default" onChange={() => undefined} language="es" />)

    const note = await screen.findByTestId('profile-recommendation')
    expect(note.textContent).toContain('WER 1,66 %')
    expect(note.textContent).toContain('Orientativo')
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/quality-profiles?language=es')
  })

  it('sin medición lo dice y no recomienda ningún perfil', async () => {
    stubFetch(payload(UNMEASURED))
    render(<ProfileSelector value={null} onChange={() => undefined} language="fr" />)

    const note = await screen.findByTestId('profile-recommendation')
    expect(note.textContent).toContain('No hay perfil recomendado (sin medición')
    expect(screen.queryByText('Medido')).toBeNull()
  })

  it('disabled bloquea el grupo y un fallo de carga se anuncia', async () => {
    stubFetch(payload(MEASURED))
    const { unmount } = render(
      <ProfileSelector value={null} onChange={() => undefined} disabled />,
    )
    const group = await screen.findByRole('group', { name: 'Perfil de calidad' })
    expect(group).toHaveProperty('disabled', true)
    unmount()

    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockRejectedValue(new Error('caído')))
    render(<ProfileSelector value={null} onChange={() => undefined} />)
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('caído')
    })
  })

  it('al cambiar el idioma vuelve a pedir la recomendación', async () => {
    const fetchMock = stubFetch(payload(MEASURED))
    const { rerender } = render(
      <ProfileSelector value={null} onChange={() => undefined} language="es" />,
    )
    await screen.findByTestId('profile-recommendation')

    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(payload(UNMEASURED)),
    } as unknown as Response)
    rerender(<ProfileSelector value={null} onChange={() => undefined} language="fr" />)

    await waitFor(() => {
      expect(screen.getByTestId('profile-recommendation').textContent).toContain(
        'No hay perfil recomendado (sin medición',
      )
    })
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/quality-profiles?language=fr')
  })
})
