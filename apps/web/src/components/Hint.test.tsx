import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { InfoTip, Term } from './Hint'
import { DeviceLabel, PrecisionLabel, ProcessingProfileLabel } from './TechTerms'
import { setLang } from '../i18n/i18n'

afterEach(cleanup)

describe('Hint', () => {
  it.each([['es', 'Nativa'], ['en', 'Native']] as const)('labels native precision in %s', (lang, label) => {
    setLang(lang)
    render(<PrecisionLabel precision="native" />)
    expect(screen.getByRole('button', { name: label })).toBeDefined()
  })

  it('Term es un botón enfocable con la definición asociada', () => {
    render(<Term definition="term.vad.def">VAD</Term>)
    const term = screen.getByRole('button', { name: 'VAD' })
    expect(term.getAttribute('aria-describedby')).toBeTruthy()
    expect(document.body.textContent).toContain('omite silencios y ruido')
  })

  it('Term plano usa title (para controles que no admiten botones dentro)', () => {
    render(<Term definition="term.vad.def" plain>VAD</Term>)
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.getByTitle(/omite silencios/i).textContent).toBe('VAD')
  })

  it('InfoTip abre una explicación larga', () => {
    render(
      <InfoTip label="diar.help.label">
        <p>Explicación larga</p>
      </InfoTip>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Cómo funciona la detección de hablantes' }))
    expect(screen.getByText('Explicación larga')).toBeDefined()
  })

  it('dispositivo, precisión y perfil técnicos traducen sus definiciones', () => {
    render(
      <>
        <DeviceLabel device="cuda" />
        <DeviceLabel device="npu" />
        <PrecisionLabel precision="int8" />
        <ProcessingProfileLabel name="quality" />
      </>,
    )
    expect(screen.getByRole('button', { name: 'GPU (CUDA)' })).toBeDefined()
    expect(screen.getByText('npu')).toBeDefined() // desconocido: texto tal cual
    expect(screen.getByRole('button', { name: 'int8' })).toBeDefined()
    expect(screen.getByRole('button', { name: 'Calidad' })).toBeDefined()
    expect(document.body.textContent).toContain('Enteros de 8 bits')
  })
})
