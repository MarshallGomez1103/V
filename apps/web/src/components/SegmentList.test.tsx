import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SegmentList } from './SegmentList'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function stubFetch(body: unknown, ok = true, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(body),
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('SegmentList', () => {
  it('no hace fetch ni renderiza cuando transcriptId es null', () => {
    const fetchMock = stubFetch({ segments: [] })

    const { container } = render(<SegmentList transcriptId={null} />)

    expect(fetchMock).not.toHaveBeenCalled()
    expect(container.innerHTML).toBe('')
  })

  it('lista los segmentos en orden con marcas de tiempo mm:ss.d', async () => {
    const fetchMock = stubFetch({
      segments: [
        { id: 's1', start_ms: 0, end_ms: 2500, text: 'Hola a todos.' },
        { id: 's2', start_ms: 2500, end_ms: 65300, text: 'Segunda\nlínea' },
      ],
    })

    render(<SegmentList transcriptId="tr 1" />)

    const list = await screen.findByRole('list')
    const items = within(list).getAllByRole('listitem')
    expect(items.map((item) => item.querySelector('time')?.textContent)).toEqual(
      ['00:00.0 → 00:02.5', '00:02.5 → 01:05.3'],
    )
    expect(items.map((item) => item.querySelector('p')?.textContent)).toEqual(
      ['Hola a todos.', 'Segunda\nlínea'],
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/transcripts/tr%201/segments',
      expect.objectContaining({ headers: { Accept: 'application/json' } }),
    )
  })

  it('muestra un estado vacío cuando no hay segmentos', async () => {
    stubFetch({ segments: [] })

    render(<SegmentList transcriptId="tr-1" />)

    expect(
      await screen.findByText(/no contiene segmentos/i),
    ).toBeDefined()
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('muestra un error seguro cuando la API falla', async () => {
    stubFetch(
      { detail: { code: 'transcript_not_found', message: 'raw' } },
      false,
      404,
    )

    render(<SegmentList transcriptId="tr-1" />)

    expect((await screen.findByRole('alert')).textContent).toBe(
      'La transcripción ya no existe.',
    )
  })
})
