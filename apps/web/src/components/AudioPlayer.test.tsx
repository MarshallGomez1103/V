import { cleanup, fireEvent, render, screen } from '@testing-library/react'
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
    // Sin los controles nativos (píldora del navegador): los controles son de la app.
    expect(audio.hasAttribute('controls')).toBe(false)
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

  it('notifica la posición en ms enteros con timeupdate y seeked', () => {
    const onTimeUpdate = vi.fn()
    render(
      <AudioPlayer
        mediaAssetId="a1"
        seekToMs={null}
        seekNonce={0}
        onTimeUpdate={onTimeUpdate}
      />,
    )
    const audio = screen.getByLabelText<HTMLAudioElement>(
      'Reproductor del original',
    )

    audio.currentTime = 1.2344
    fireEvent(audio, new Event('timeupdate'))
    audio.currentTime = 90
    fireEvent(audio, new Event('seeked'))

    expect(onTimeUpdate.mock.calls).toEqual([[1234], [90_000]])
  })

  it('sin onTimeUpdate los eventos nativos no fallan', () => {
    render(<AudioPlayer mediaAssetId="a1" seekToMs={null} seekNonce={0} />)
    const audio = screen.getByLabelText<HTMLAudioElement>(
      'Reproductor del original',
    )

    expect(() => fireEvent(audio, new Event('timeupdate'))).not.toThrow()
  })

  it('el botón alterna reproducir y pausar según los eventos del audio', () => {
    const play = vi
      .spyOn(HTMLMediaElement.prototype, 'play')
      .mockImplementation(() => Promise.resolve())
    const pause = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined)
    render(<AudioPlayer mediaAssetId="a1" seekToMs={null} seekNonce={0} durationMs={90_000} />)
    const audio = screen.getByLabelText<HTMLAudioElement>('Reproductor del original')

    fireEvent.click(screen.getByRole('button', { name: 'Reproducir' }))
    expect(play).toHaveBeenCalledTimes(1)
    // jsdom no reproduce: se simula que el medio ya no está en pausa.
    Object.defineProperty(audio, 'paused', { value: false, configurable: true })
    fireEvent(audio, new Event('play'))

    fireEvent.click(screen.getByRole('button', { name: 'Pausar' }))
    expect(pause).toHaveBeenCalledTimes(1)
    fireEvent(audio, new Event('pause'))
    expect(screen.getByRole('button', { name: 'Reproducir' })).toBeDefined()
  })

  it('muestra el tiempo y la duración conocida antes de que el navegador la mida', () => {
    render(<AudioPlayer mediaAssetId="a1" seekToMs={null} seekNonce={0} durationMs={107_000} />)
    const audio = screen.getByLabelText<HTMLAudioElement>('Reproductor del original')

    expect(screen.getByLabelText('Tiempo transcurrido y duración').textContent).toContain('0:00')
    expect(screen.getByLabelText('Tiempo transcurrido y duración').textContent).toContain('1:47')

    audio.currentTime = 65
    fireEvent(audio, new Event('timeupdate'))
    expect(screen.getByLabelText('Tiempo transcurrido y duración').textContent).toContain('1:05')
  })

  it('la barra de posición salta y los botones adelantan y retroceden 5 s', () => {
    render(<AudioPlayer mediaAssetId="a1" seekToMs={null} seekNonce={0} durationMs={100_000} />)
    const audio = screen.getByLabelText<HTMLAudioElement>('Reproductor del original')

    fireEvent.change(screen.getByRole('slider', { name: 'Posición en la grabación' }), {
      target: { value: '30' },
    })
    expect(audio.currentTime).toBe(30)

    fireEvent.click(screen.getByRole('button', { name: 'Adelantar 5 s' }))
    expect(audio.currentTime).toBe(35)
    fireEvent.click(screen.getByRole('button', { name: 'Retroceder 5 s' }))
    expect(audio.currentTime).toBe(30)
  })

  it('silencia, cambia el volumen y rota la velocidad', () => {
    render(<AudioPlayer mediaAssetId="a1" seekToMs={null} seekNonce={0} />)
    const audio = screen.getByLabelText<HTMLAudioElement>('Reproductor del original')

    fireEvent.click(screen.getByRole('button', { name: 'Silenciar' }))
    expect(audio.muted).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Quitar el silencio' }))
    expect(audio.muted).toBe(false)

    fireEvent.change(screen.getByRole('slider', { name: 'Volumen' }), { target: { value: '0.5' } })
    expect(audio.volume).toBe(0.5)

    fireEvent.click(screen.getByRole('button', { name: /Velocidad 1×/ }))
    expect(audio.playbackRate).toBe(1.25)
  })
})
