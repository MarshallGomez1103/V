import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { setLang } from '../i18n/i18n'
import type { TrimRange } from '../lib/trimRange'
import { TrimControls } from './TrimControls'

afterEach(() => {
  cleanup()
  setLang('es')
})

function setup(value: TrimRange | null = null, durationMs: number | null = 60_000, currentMs = 0) {
  const onChange = vi.fn()
  const onSeek = vi.fn()
  render(
    <TrimControls durationMs={durationMs} value={value} currentMs={currentMs} onChange={onChange} onSeek={onSeek} />,
  )
  return { onChange, onSeek }
}

describe('TrimControls', () => {
  it('el tope del deslizador cuenta como el final real cuando la duración no es múltiplo de 100 ms', () => {
    const { onChange } = setup({ startMs: 0, endMs: 30_000 }, 60_050)
    // El navegador limita el range al último múltiplo del paso (60 000).
    fireEvent.change(screen.getByRole('slider', { name: 'Fin' }), { target: { value: '60000' } })
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('ArrowRight sobre «Inicio» suma 100 ms', () => {
    const { onChange } = setup({ startMs: 5000, endMs: 20_000 })
    const start = screen.getByRole<HTMLInputElement>('slider', { name: 'Inicio' })
    fireEvent.keyDown(start, { key: 'ArrowRight' })
    expect(onChange).toHaveBeenCalledWith({ startMs: 5100, endMs: 20_000 })
    fireEvent.keyDown(start, { key: 'ArrowLeft' })
    expect(onChange).toHaveBeenLastCalledWith({ startMs: 4900, endMs: 20_000 })
  })

  it('los deslizadores son nativos, con paso de 100 ms y valor en mm:ss', () => {
    setup({ startMs: 10_000, endMs: 20_000 })
    const start = screen.getByRole<HTMLInputElement>('slider', { name: 'Inicio' })
    expect(start.type).toBe('range')
    expect(start.step).toBe('100')
    expect(start.getAttribute('aria-valuetext')).toBe('00:10')
    expect(screen.getByRole('slider', { name: 'Fin' }).getAttribute('aria-valuetext')).toBe('00:20')
  })

  it('con Fin igual o antes de Inicio muestra el mensaje y no deja reproducir', () => {
    setup({ startMs: 20_000, endMs: 20_000 })
    expect(screen.getByText('El fin debe ser posterior al inicio.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Reproducir tramo' }).hasAttribute('disabled')).toBe(true)
  })

  it('muestra el mensaje en inglés', () => {
    setLang('en')
    setup({ startMs: 0, endMs: 500 })
    expect(screen.getByText('The range must be at least 1 second long.')).toBeTruthy()
  })

  it('«Reproducir tramo» pide reproducir desde el inicio con parada en el fin', () => {
    const { onSeek } = setup({ startMs: 10_000, endMs: 25_000 })
    fireEvent.click(screen.getByRole('button', { name: 'Reproducir tramo' }))
    expect(onSeek).toHaveBeenCalledWith(10_000, 25_000)
  })

  it('«Inicio aquí» y «Fin aquí» toman la posición del reproductor', () => {
    const { onChange } = setup({ startMs: 0, endMs: 30_000 }, 60_000, 12_340)
    fireEvent.click(screen.getByRole('button', { name: 'Inicio aquí' }))
    expect(onChange).toHaveBeenLastCalledWith({ startMs: 12_300, endMs: 30_000 })
    fireEvent.click(screen.getByRole('button', { name: 'Fin aquí' }))
    expect(onChange).toHaveBeenLastCalledWith({ startMs: 0, endMs: 12_300 })
  })

  it('un tramo que cubre toda la grabación vuelve a «sin recorte»', () => {
    const { onChange } = setup({ startMs: 5000, endMs: 60_000 })
    fireEvent.keyDown(screen.getByRole('slider', { name: 'Inicio' }), { key: 'ArrowLeft' })
    expect(onChange).toHaveBeenLastCalledWith({ startMs: 4900, endMs: 60_000 })
    fireEvent.change(screen.getByRole('slider', { name: 'Inicio' }), { target: { value: '0' } })
    expect(onChange).toHaveBeenLastCalledWith(null)
  })

  it('«Quitar recorte» vuelve a la grabación completa', () => {
    const { onChange } = setup({ startMs: 5000, endMs: 20_000 })
    fireEvent.click(screen.getByRole('button', { name: 'Quitar recorte' }))
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('sin recorte lo dice y «Quitar recorte» está deshabilitado', () => {
    setup(null)
    expect(screen.getByText('Se transcribe la grabación completa.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Quitar recorte' }).hasAttribute('disabled')).toBe(true)
  })

  it('con un tramo válido resume lo transcrito y lo omitido', () => {
    setup({ startMs: 10_000, endMs: 40_000 })
    expect(screen.getByText('00:10–00:40 de 01:00 (00:30 sin transcribir)')).toBeTruthy()
  })

  it('sin duración del servidor deshabilita los controles y avisa', () => {
    setup(null, null)
    expect(screen.getByText(/no se conoce la duración/i)).toBeTruthy()
    for (const slider of screen.getAllByRole('slider')) {
      expect(slider.hasAttribute('disabled')).toBe(true)
    }
    for (const button of screen.getAllByRole('button')) {
      expect(button.hasAttribute('disabled')).toBe(true)
    }
  })
})
