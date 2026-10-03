import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Speaker } from '../api/speakers'
import { SegmentSpeakerSelect } from './SegmentSpeakerSelect'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const SPEAKERS: Speaker[] = [
  { id: 'a', name: 'Ana', color: '#112233', segment_count: 2 },
  { id: 'b', name: 'Beto', color: '#445566', segment_count: 1 },
]

function stubFetch(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status < 300,
    status,
    json: () => Promise.resolve(body),
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function select() {
  return screen.getByRole('combobox', { name: /Hablante del segmento s1/ })
}

describe('SegmentSpeakerSelect', () => {
  it('muestra el hablante actual con su color', () => {
    const { container } = render(
      <SegmentSpeakerSelect segmentId="s1" speakerId="a" speakers={SPEAKERS} />,
    )

    expect((select() as HTMLSelectElement).value).toBe('a')
    const chip = container.querySelector<HTMLElement>('.voz-segment-speaker__chip')
    expect(chip?.style.backgroundColor).toBe('rgb(17, 34, 51)')
  })

  it('sin hablante selecciona la opción vacía', () => {
    render(
      <SegmentSpeakerSelect segmentId="s1" speakerId={null} speakers={SPEAKERS} />,
    )

    expect((select() as HTMLSelectElement).value).toBe('')
  })

  it('reasigna con PUT y avisa con onChanged', async () => {
    const fetchMock = stubFetch({ id: 's1', speaker_id: 'b' })
    const onChanged = vi.fn()
    render(
      <SegmentSpeakerSelect
        segmentId="s1"
        speakerId="a"
        speakers={SPEAKERS}
        onChanged={onChanged}
      />,
    )

    fireEvent.change(select(), { target: { value: 'b' } })

    await waitFor(() => {
      expect(onChanged).toHaveBeenCalledTimes(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/segments/s1/speaker',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ speaker_id: 'b' }),
      }),
    )
  })

  it('"Sin hablante" envía null', async () => {
    const fetchMock = stubFetch({ id: 's1', speaker_id: null })
    render(
      <SegmentSpeakerSelect segmentId="s1" speakerId="a" speakers={SPEAKERS} />,
    )

    fireEvent.change(select(), { target: { value: '' } })

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled()
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/segments/s1/speaker',
      expect.objectContaining({ body: JSON.stringify({ speaker_id: null }) }),
    )
  })

  it('un error de la API se muestra y no llama a onChanged', async () => {
    stubFetch({ detail: { code: 'segment_speaker_invalid', message: 'x' } }, 409)
    const onChanged = vi.fn()
    render(
      <SegmentSpeakerSelect
        segmentId="s1"
        speakerId="a"
        speakers={SPEAKERS}
        onChanged={onChanged}
      />,
    )

    fireEvent.change(select(), { target: { value: 'b' } })

    expect((await screen.findByRole('alert')).textContent).toMatch(
      /no pertenece a la transcripción/,
    )
    expect(onChanged).not.toHaveBeenCalled()
  })
})
