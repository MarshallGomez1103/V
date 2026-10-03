import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { DiarizationModelState } from '../hooks/useDiarizationModel'
import type { ModelView, TaskView } from '../api/models'

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
    expect(screen.queryByRole('tab', { name: 'Automático' })).toBeNull()
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

    fireEvent.click(screen.getByRole('tab', { name: 'Exacto' }))
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

    expect(screen.getByRole('tab', { name: 'Rango' }).getAttribute('aria-selected')).toBe('true')
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

    fireEvent.click(screen.getByRole('tab', { name: 'Automático' }))

    expect(onChange).toHaveBeenCalledWith({ enabled: true, speakers: {} })
  })

  it('disabled bloquea todos los controles', () => {
    render(<DiarizationOptions value={ON} onChange={() => undefined} disabled />)

    expect(screen.getByRole('switch', { name: 'Detectar quién habla' })).toHaveProperty(
      'disabled',
      true,
    )
    expect(screen.getByRole('tab', { name: 'Automático' })).toHaveProperty('disabled', true)
    expect(screen.getByRole('tab', { name: 'Rango' })).toHaveProperty('disabled', true)
  })

  describe('modelo de hablantes', () => {
    const MODEL: ModelView = {
      key: 'diarization:sherpa-default',
      provider_id: 'diarization',
      kind: 'diarization',
      requires: 'diarization',
      runtime_available: true,
      model_id: 'sherpa-default',
      display_name: 'Hablantes',
      source: null,
      revision: null,
      license: 'MIT',
      multilingual: true,
      profile: null,
      size_bytes: 33_488_994,
      installed: false,
      disk_bytes: null,
      external: [],
    }
    const state = (patch: Partial<DiarizationModelState>): DiarizationModelState => ({
      status: 'missing',
      model: MODEL,
      task: null,
      error: null,
      download: vi.fn(),
      cancel: vi.fn(),
      retry: vi.fn(),
      ...patch,
    })

    it('si falta, ofrece descargarlo en línea con su tamaño', () => {
      const model = state({})
      render(<DiarizationOptions value={ON} onChange={() => undefined} model={model} />)

      expect(screen.getByText('Falta el modelo de hablantes')).toBeDefined()
      const button = screen.getByRole('button', { name: /descargar modelo de hablantes \(33\sMB\)/i })
      fireEvent.click(button)
      expect(model.download).toHaveBeenCalledTimes(1)
    })

    it('no muestra nada del modelo con los hablantes apagados', () => {
      render(<DiarizationOptions value={OFF} onChange={() => undefined} model={state({})} />)
      expect(screen.queryByText('Falta el modelo de hablantes')).toBeNull()
    })

    it('descargando: muestra progreso y permite cancelar', () => {
      const task = { done_bytes: 10_000_000, total_bytes: 33_488_994, state: 'running' } as TaskView
      const model = state({ status: 'downloading', task })
      render(<DiarizationOptions value={ON} onChange={() => undefined} model={model} />)

      expect(screen.getByText(/descargando: 29 %/i)).toBeDefined()
      fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
      expect(model.cancel).toHaveBeenCalledTimes(1)
    })

    it('listo: lo dice; sin extra: explica y no ofrece descargar; con error: reintenta', () => {
      const { rerender } = render(
        <DiarizationOptions value={ON} onChange={() => undefined} model={state({ status: 'ready' })} />,
      )
      expect(screen.getByText('Modelo de hablantes instalado.')).toBeDefined()

      rerender(
        <DiarizationOptions value={ON} onChange={() => undefined} model={state({ status: 'unavailable' })} />,
      )
      expect(screen.getByText(/no se puede usar aquí/i)).toBeDefined()
      expect(screen.queryByRole('button', { name: /descargar/i })).toBeNull()

      const model = state({ status: 'error', error: 'sin conexión' })
      rerender(<DiarizationOptions value={ON} onChange={() => undefined} model={model} />)
      fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
      expect(model.retry).toHaveBeenCalledTimes(1)
    })
  })
})
