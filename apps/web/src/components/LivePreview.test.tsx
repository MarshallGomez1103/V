import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { LivePreview } from './LivePreview'

afterEach(cleanup)

describe('LivePreview', () => {
  it('sin segmentos explica qué pasa y qué va a aparecer', () => {
    render(<LivePreview segments={[]} />)
    expect(screen.getByRole('heading', { name: 'Texto en vivo' })).toBeDefined()
    expect(screen.getByText('Esperando los primeros segmentos…')).toBeDefined()
    expect(screen.getByText(/aparecerá aquí en cuanto el motor confirme/i)).toBeDefined()
  })

  it('lista los segmentos con su marca de tiempo y cuenta hasta dónde llega', () => {
    render(
      <LivePreview
        segments={[
          { start_ms: 0, end_ms: 4000, text: 'Buenos días.' },
          { start_ms: 4000, end_ms: 65_000, text: 'Hoy vemos el proyecto.' },
        ]}
      />,
    )
    const list = screen.getByRole('region', { name: 'Segmentos en vivo' })
    const rows = within(list).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(rows[1]?.textContent).toContain('00:04.0')
    expect(rows[1]?.textContent).toContain('Hoy vemos el proyecto.')
    expect(screen.getByText('2 segmentos hasta 1:05')).toBeDefined()
  })

  it('en inglés habla inglés', async () => {
    const { setLang } = await import('../i18n/i18n')
    setLang('en')
    render(<LivePreview segments={[{ start_ms: 0, end_ms: 1000, text: 'Hi.' }]} />)
    expect(screen.getByRole('heading', { name: 'Live text' })).toBeDefined()
    expect(screen.getByText('1 segment up to 0:01')).toBeDefined()
  })
})
