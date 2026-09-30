import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { exportDocumentUrl } from '../api/exportDocument'
import { ExportMenu } from './ExportMenu'

afterEach(cleanup)

function downloadHref(): string | null {
  return screen.getByRole('link', { name: 'Descargar' }).getAttribute('href')
}

describe('exportDocumentUrl', () => {
  it('codifica el id y omite opciones apagadas', () => {
    expect(
      exportDocumentUrl('t 1', { format: 'srt', timestamps: false, groupBySpeaker: false }),
    ).toBe('/api/transcripts/t%201/export?format=srt')
  })

  it('no envía opciones a formatos que no las soportan', () => {
    expect(
      exportDocumentUrl('t1', { format: 'json', timestamps: true, groupBySpeaker: true }),
    ).toBe('/api/transcripts/t1/export?format=json')
  })
})

describe('ExportMenu', () => {
  it('ofrece descarga de TXT por defecto', () => {
    render(<ExportMenu transcriptId="t1" />)

    const link = screen.getByRole('link', { name: 'Descargar' })
    expect(link.hasAttribute('download')).toBe(true)
    expect(downloadHref()).toBe('/api/transcripts/t1/export?format=txt')
  })

  it('añade tiempos y agrupación al enlace', () => {
    render(<ExportMenu transcriptId="t1" />)

    fireEvent.click(screen.getByLabelText('Incluir tiempos'))
    fireEvent.click(screen.getByLabelText('Agrupar por speaker'))

    expect(downloadHref()).toBe(
      '/api/transcripts/t1/export?format=txt&timestamps=true&group_by_speaker=true',
    )
  })

  it('deshabilita las opciones en formatos que no las soportan', () => {
    render(<ExportMenu transcriptId="t1" />)
    fireEvent.click(screen.getByLabelText('Incluir tiempos'))

    fireEvent.change(screen.getByLabelText('Formato'), { target: { value: 'vtt' } })

    expect(screen.getByLabelText<HTMLInputElement>('Incluir tiempos').disabled).toBe(true)
    expect(screen.getByLabelText<HTMLInputElement>('Agrupar por speaker').disabled).toBe(
      true,
    )
    expect(downloadHref()).toBe('/api/transcripts/t1/export?format=vtt')

    fireEvent.change(screen.getByLabelText('Formato'), { target: { value: 'markdown' } })

    expect(downloadHref()).toBe(
      '/api/transcripts/t1/export?format=markdown&timestamps=true',
    )
  })
})
