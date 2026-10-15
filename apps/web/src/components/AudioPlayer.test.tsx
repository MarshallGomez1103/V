import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AudioPlayer } from './AudioPlayer'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('AudioPlayer', () => {
  it('dos vistas del mismo audio tienen controles con identificadores distintos', () => {
    const { container } = render(<>
      <AudioPlayer mediaAssetId="same" seekToMs={null} seekNonce={0} />
      <AudioPlayer mediaAssetId="same" seekToMs={null} seekNonce={0} />
    </>)
    const ids = [...container.querySelectorAll('[id]')].map((element) => element.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('los atajos dentro de otro reproductor solo controlan ese reproductor', () => {
    render(<>
      <AudioPlayer mediaAssetId="result" seekToMs={null} seekNonce={0} />
      <AudioPlayer mediaAssetId="history" seekToMs={null} seekNonce={0} />
    </>)
    const players = screen.getAllByRole('group', { name: 'Controles de reproducción' })
    const audio = screen.getAllByLabelText<HTMLAudioElement>('Reproductor del original')
    const target = within(players[1]!).getAllByRole('button')[0]!
    fireEvent.keyDown(target, { key: 'ArrowRight' })
    expect(audio[0]!.currentTime).toBe(0)
    expect(audio[1]!.currentTime).toBe(5)
  })

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

  it('con src reproduce esa URL (audio sintetizado) en vez del original', () => {
    render(
      <AudioPlayer
        mediaAssetId="job 1"
        src="/api/synthesis/job%201/audio"
        seekToMs={null}
        seekNonce={0}
        durationMs={65_000}
      />,
    )

    const audio = screen.getByLabelText<HTMLAudioElement>('Reproductor del original')
    expect(audio.getAttribute('src')).toBe('/api/synthesis/job%201/audio')
    expect(screen.getByLabelText('Tiempo transcurrido y duración').textContent).toContain('1:05')
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

    fireEvent.click(screen.getByRole('button', { name: /^Reproducir/ }))
    expect(play).toHaveBeenCalledTimes(1)
    // jsdom no reproduce: se simula que el medio ya no está en pausa.
    Object.defineProperty(audio, 'paused', { value: false, configurable: true })
    fireEvent(audio, new Event('play'))

    fireEvent.click(screen.getByRole('button', { name: /^Pausar/ }))
    expect(pause).toHaveBeenCalledTimes(1)
    fireEvent(audio, new Event('pause'))
    expect(screen.getByRole('button', { name: /^Reproducir/ })).toBeDefined()
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

    fireEvent.click(screen.getByRole('button', { name: /^Adelantar 5 s/ }))
    expect(audio.currentTime).toBe(35)
    fireEvent.click(screen.getByRole('button', { name: /^Retroceder 5 s/ }))
    expect(audio.currentTime).toBe(30)
  })

  it('silencia, cambia el volumen (hasta 100 % con el propio audio) y la velocidad', () => {
    render(<AudioPlayer mediaAssetId="a1" seekToMs={null} seekNonce={0} />)
    const audio = screen.getByLabelText<HTMLAudioElement>('Reproductor del original')

    fireEvent.click(screen.getByRole('button', { name: 'Silenciar' }))
    expect(audio.muted).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Quitar el silencio' }))
    expect(audio.muted).toBe(false)

    fireEvent.change(screen.getByRole('slider', { name: 'Volumen' }), { target: { value: '50' } })
    expect(audio.volume).toBe(0.5)
    expect(screen.queryByText(/puede saturarse/i)).toBeNull()

    fireEvent.click(screen.getByRole('combobox', { name: 'Velocidad' }))
    fireEvent.click(screen.getByRole('option', { name: '1.25×' }))
    expect(audio.playbackRate).toBe(1.25)
  })

  it('la velocidad ofrece 0.5, 0.75, 1, 1.25, 1.5 y 2', () => {
    render(<AudioPlayer mediaAssetId="a1" seekToMs={null} seekNonce={0} />)
    fireEvent.click(screen.getByRole('combobox', { name: 'Velocidad' }))
    expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual([
      '0.5×',
      '0.75×',
      '1× (normal)',
      '1.25×',
      '1.5×',
      '2×',
    ])
  })
})

describe('AudioPlayer: volumen por encima de 100 %', () => {
  let created: { gain: { gain: { value: number } }; sources: number }[]

  beforeEach(() => {
    created = []
    class FakeContext {
      destination = {}
      state = 'suspended'
      info = { gain: { gain: { value: 1 } }, sources: 0 }
      constructor() {
        created.push(this.info)
      }
      createGain() {
        return { ...this.info.gain, connect: () => undefined }
      }
      createMediaElementSource() {
        this.info.sources += 1
        return { connect: () => undefined }
      }
      resume() {
        return Promise.resolve()
      }
      close() {
        return Promise.resolve()
      }
    }
    vi.stubGlobal('AudioContext', FakeContext)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('permite hasta 300 %, avisa de la saturación y crea el GainNode una sola vez', () => {
    render(<AudioPlayer mediaAssetId="a1" seekToMs={null} seekNonce={0} />)
    const audio = screen.getByLabelText<HTMLAudioElement>('Reproductor del original')
    const slider = screen.getByRole<HTMLInputElement>('slider', { name: 'Volumen' })
    expect(slider.max).toBe('300')
    expect(created).toHaveLength(0)

    fireEvent.change(slider, { target: { value: '200' } })
    expect(screen.getByText(/puede saturarse/i)).toBeDefined()
    expect(created).toHaveLength(1)
    expect(created[0]?.sources).toBe(1)
    expect(audio.volume).toBe(1)

    fireEvent.change(slider, { target: { value: '300' } })
    fireEvent.change(slider, { target: { value: '150' } })
    expect(created).toHaveLength(1)
    expect(created[0]?.sources).toBe(1)

    fireEvent.change(slider, { target: { value: '100' } })
    expect(screen.queryByText(/puede saturarse/i)).toBeNull()
  })

  it('sin Web Audio el tope queda en 100 %', () => {
    vi.stubGlobal('AudioContext', undefined)
    render(<AudioPlayer mediaAssetId="a1" seekToMs={null} seekNonce={0} />)
    expect(screen.getByRole<HTMLInputElement>('slider', { name: 'Volumen' }).max).toBe('100')
  })
})

describe('AudioPlayer: atajos y muestras', () => {
  it('Espacio reproduce o pausa y las flechas mueven 5 s, salvo al escribir', () => {
    const play = vi
      .spyOn(HTMLMediaElement.prototype, 'play')
      .mockImplementation(() => Promise.resolve())
    render(
      <>
        <input aria-label="caja" />
        <AudioPlayer mediaAssetId="a1" seekToMs={null} seekNonce={0} durationMs={100_000} />
      </>,
    )
    const audio = screen.getByLabelText<HTMLAudioElement>('Reproductor del original')

    fireEvent.keyDown(document.body, { code: 'Space', key: ' ' })
    expect(play).toHaveBeenCalledTimes(1)

    audio.currentTime = 20
    fireEvent.keyDown(document.body, { key: 'ArrowRight' })
    expect(audio.currentTime).toBe(25)
    fireEvent.keyDown(document.body, { key: 'ArrowLeft' })
    expect(audio.currentTime).toBe(20)

    fireEvent.keyDown(screen.getByLabelText('caja'), { code: 'Space', key: ' ' })
    fireEvent.keyDown(screen.getByLabelText('caja'), { key: 'ArrowRight' })
    expect(play).toHaveBeenCalledTimes(1)
    expect(audio.currentTime).toBe(20)
  })

  it('un seek con fin pausa al llegar a ese instante', () => {
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(() => Promise.resolve())
    const pause = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined)
    const { rerender } = render(
      <AudioPlayer mediaAssetId="a1" seekToMs={null} seekNonce={0} durationMs={100_000} />,
    )
    rerender(
      <AudioPlayer mediaAssetId="a1" seekToMs={5000} seekNonce={1} stopAtMs={9000} durationMs={100_000} />,
    )
    const audio = screen.getByLabelText<HTMLAudioElement>('Reproductor del original')

    audio.currentTime = 8
    fireEvent(audio, new Event('timeupdate'))
    expect(pause).not.toHaveBeenCalled()
    audio.currentTime = 9.1
    fireEvent(audio, new Event('timeupdate'))
    expect(pause).toHaveBeenCalledTimes(1)
  })
})
