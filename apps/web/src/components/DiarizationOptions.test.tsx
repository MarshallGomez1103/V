import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  DiarizationOptions,
  type DiarizationRequest,
} from './DiarizationOptions'

afterEach(cleanup)

const OFF: DiarizationRequest = { enabled: false, speakers: {} }
const ON: DiarizationRequest = { enabled: true, speakers: {} }

describe('DiarizationOptions', () => {
  it('oculta los modos mientras la detección está apagada', () => {
    render(<DiarizationOptions value={OFF} onChange={() => undefined} />)

    expect(
      screen.getByRole('switch', { name: 'Detectar quién habla' }).getAttribute('aria-checked'),
    ).toBe('false')
    expect(screen.queryByLabelText('Automático')).toBeNull()
  })

  it('activar el interruptor emite enabled: true', () => {
    const onChange = vi.fn()
    render(<DiarizationOptions value={OFF} onChange={onChange} />)

    fireEvent.click(screen.getByRole('switch', { name: 'Detectar quién habla' }))

    expect(onChange).toHaveBeenCalledWith({ enabled: true, speakers: {} })
  })

  it('modo Exacto emite un número de hablantes editable', () => {
    const onChange = vi.fn()
    const { rerender } = render(<DiarizationOptions value={ON} onChange={onChange} />)

    fireEvent.click(screen.getByLabelText('Exacto'))
    expect(onChange).toHaveBeenLastCalledWith({
      enabled: true,
      speakers: { exact: 2 },
    })

    rerender(
      <DiarizationOptions
        value={{ enabled: true, speakers: { exact: 2 } }}
        onChange={onChange}
      />,
    )
    fireEvent.change(screen.getByLabelText('Número de hablantes'), {
      target: { value: '3' },
    })
    expect(onChange).toHaveBeenLastCalledWith({
      enabled: true,
      speakers: { exact: 3 },
    })
  })

  it('modo Rango emite mínimo y máximo sin invertirlos', () => {
    const onChange = vi.fn()
    render(
      <DiarizationOptions
        value={{ enabled: true, speakers: { minimum: 2, maximum: 4 } }}
        onChange={onChange}
      />,
    )

    expect(screen.getByLabelText('Rango')).toHaveProperty('checked', true)
    fireEvent.change(screen.getByLabelText('Mínimo'), { target: { value: '6' } })
    expect(onChange).toHaveBeenLastCalledWith({
      enabled: true,
      speakers: { minimum: 6, maximum: 6 },
    })

    fireEvent.change(screen.getByLabelText('Máximo'), { target: { value: '1' } })
    expect(onChange).toHaveBeenLastCalledWith({
      enabled: true,
      speakers: { minimum: 1, maximum: 1 },
    })
  })

  it('volver a Automático limpia las restricciones', () => {
    const onChange = vi.fn()
    render(
      <DiarizationOptions
        value={{ enabled: true, speakers: { exact: 3 } }}
        onChange={onChange}
      />,
    )

    fireEvent.click(screen.getByLabelText('Automático'))

    expect(onChange).toHaveBeenCalledWith({ enabled: true, speakers: {} })
  })

  it('disabled bloquea todos los controles', () => {
    render(<DiarizationOptions value={ON} onChange={() => undefined} disabled />)

    expect(screen.getByRole('switch', { name: 'Detectar quién habla' })).toHaveProperty(
      'disabled',
      true,
    )
    // El fieldset deshabilitado bloquea los radios (:disabled lo refleja).
    expect(screen.getByLabelText('Automático').matches(':disabled')).toBe(true)
    expect(screen.getByLabelText('Rango').matches(':disabled')).toBe(true)
  })
})
