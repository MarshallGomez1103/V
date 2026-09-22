import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AudioPlayer } from './AudioPlayer'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('AudioPlayer', () => {
  it('no renderiza nada sin mediaAssetId', () => {
    const { container } = render(
      <AudioPlayer mediaAssetId={null} seekToMs={null} seekNonce={0} />,
    )

    expect(container.innerHTML).toBe('')
  })

  it('apunta al original del asset con la ruta codificada', () => {
    render(<AudioPlayer mediaAssetId="asset 1" seekToMs={null} seekNonce={0} />)

    const audio = screen.getByLabelText<HTMLAudioElement>(
      'Reproductor del original',
    )
    expect(audio.tagName).toBe('AUDIO')
    expect(audio.getAttribute('src')).toBe('/api/media/asset%201/original')
    expect(audio.hasAttribute('controls')).toBe(true)
    expect(audio.getAttribute('preload')).toBe('metadata')
  })

  it('fija currentTime y reproduce cuando cambia seekNonce', () => {
    const play = vi
      .spyOn(HTMLMediaElement.prototype, 'play')
      .mockImplementation(() => Promise.resolve())
    const { rerender } = render(
      <AudioPlayer mediaAssetId="a1" seekToMs={null} seekNonce={0} />,
    )
    const audio = screen.getByLabelText<HTMLAudioElement>(
      'Reproductor del original',
    )
    expect(play).not.toHaveBeenCalled()

    rerender(<AudioPlayer mediaAssetId="a1" seekToMs={2500} seekNonce={1} />)

    expect(audio.currentTime).toBe(2.5)
    expect(play).toHaveBeenCalledTimes(1)
  })

  it('tolera que play() sea rechazado por el navegador', () => {
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(() =>
      Promise.reject(new Error('NotAllowedError')),
    )
    const { rerender } = render(
      <AudioPlayer mediaAssetId="a1" seekToMs={null} seekNonce={0} />,
    )

    expect(() => {
      rerender(<AudioPlayer mediaAssetId="a1" seekToMs={1000} seekNonce={1} />)
    }).not.toThrow()
  })
})
