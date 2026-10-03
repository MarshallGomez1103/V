import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { exportDocumentUrl } from '../api/exportDocument'
import { ExportMenu } from './ExportMenu'

afterEach(cleanup)

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
  let clicked: { href: string; download: string }[]

  beforeEach(() => {
    clicked = []
    // jsdom no descarga: se registra el enlace que el menú dispara.
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicked.push({ href: this.getAttribute('href') ?? '', download: this.download })
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  function openMenu() {
    fireEvent.click(screen.getByRole('button', { name: 'Exportar' }))
  }

  it('ofrece los formatos de exportación y descarga TXT por defecto', () => {
    render(<ExportMenu transcriptId="t1" />)
    openMenu()

    expect(
      screen.getAllByRole('menuitem').map((item) => item.textContent),
    ).toEqual([
      'Texto (.txt)',
      'Markdown (.md)',
      'Subtítulos SRT (.srt)',
      'Subtítulos WebVTT (.vtt)',
      'JSON canónico (.json)',
    ])

    fireEvent.click(screen.getByRole('menuitem', { name: 'Texto (.txt)' }))

    expect(clicked).toEqual([
      { href: '/api/transcripts/t1/export?format=txt', download: '' },
    ])
  })

  it('añade tiempos y agrupación a la descarga', () => {
    render(<ExportMenu transcriptId="t1" />)
    openMenu()

    // Carbon cierra el menú al elegir una casilla: se reabre entre opciones.
    fireEvent.click(
      screen.getByRole('menuitemcheckbox', { name: /Incluir tiempos/ }),
    )
    openMenu()
    expect(
      screen
        .getByRole('menuitemcheckbox', { name: /Incluir tiempos/ })
        .getAttribute('aria-checked'),
    ).toBe('true')
    fireEvent.click(
      screen.getByRole('menuitemcheckbox', { name: /Agrupar por hablante/ }),
    )
    openMenu()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Markdown (.md)' }))

    expect(clicked.at(-1)?.href).toBe(
      '/api/transcripts/t1/export?format=markdown&timestamps=true&group_by_speaker=true',
    )
  })

  it('ignora las opciones en formatos que no las soportan', () => {
    render(<ExportMenu transcriptId="t1" />)
    openMenu()
    fireEvent.click(
      screen.getByRole('menuitemcheckbox', { name: /Incluir tiempos/ }),
    )
    openMenu()

    fireEvent.click(screen.getByRole('menuitem', { name: 'Subtítulos WebVTT (.vtt)' }))

    expect(clicked.at(-1)?.href).toBe('/api/transcripts/t1/export?format=vtt')
  })
})
