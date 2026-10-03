import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PROMPT_MAX_LENGTH, StyleInstructions } from './StyleInstructions'

afterEach(cleanup)

describe('StyleInstructions', () => {
  it('explica honestamente que Whisper imita el estilo y no obedece órdenes', () => {
    render(<StyleInstructions value="" onChange={() => undefined} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cómo funcionan las instrucciones de estilo' }))

    expect(screen.getByText(/no obedece órdenes como un chat/i)).toBeDefined()
    expect(screen.getByText(/«colócale comas»/)).toBeDefined()
    expect(screen.getByText(/imita su estilo/i)).toBeDefined()
    expect(screen.getByText(/ejemplo bien puntuado/i)).toBeDefined()
    expect(screen.getByText(/no es una orden: escribe un ejemplo/i)).toBeDefined()
  })

  it('emite el texto y limita a 600 caracteres', () => {
    const onChange = vi.fn()
    render(<StyleInstructions value="" onChange={onChange} />)
    const box = screen.getByPlaceholderText(/ejemplo: hola/i)

    fireEvent.change(box, { target: { value: 'Hola, qué tal.' } })
    expect(onChange).toHaveBeenLastCalledWith('Hola, qué tal.')

    fireEvent.change(box, { target: { value: 'x'.repeat(PROMPT_MAX_LENGTH + 50) } })
    expect((onChange.mock.calls.at(-1)?.[0] as string).length).toBe(PROMPT_MAX_LENGTH)
  })

  it('inserta un ejemplo con puntuación y permite borrar', () => {
    const onChange = vi.fn()
    const { rerender } = render(<StyleInstructions value="" onChange={onChange} />)
    expect(screen.queryByRole('button', { name: 'Borrar' })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Usar un ejemplo con puntuación' }))
    expect(onChange.mock.calls.at(-1)?.[0]).toMatch(/^Hola, buenas tardes\./)

    rerender(<StyleInstructions value="algo" onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'Borrar' }))
    expect(onChange).toHaveBeenLastCalledWith('')
  })

  it('deshabilitado bloquea el campo y los botones', () => {
    render(<StyleInstructions value="algo" onChange={() => undefined} disabled />)
    expect(screen.getByPlaceholderText(/ejemplo: hola/i)).toHaveProperty('disabled', true)
    expect(screen.getByRole('button', { name: 'Borrar' })).toHaveProperty('disabled', true)
  })

  it('muestra el contador de caracteres', () => {
    render(<StyleInstructions value="hola" onChange={() => undefined} />)
    expect(screen.getByText('4/600')).toBeDefined()
  })
})
