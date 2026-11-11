import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { setLang } from '../i18n/i18n'
import { SettingsMenu } from './HeaderMenus'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  setLang('es')
})

describe('SettingsMenu', () => {
  it('muestra la versión de V al abrir Ajustes', async () => {
    setLang('es')
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) =>
        Promise.resolve({
          ok: url === '/api/health',
          status: 200,
          json: () => Promise.resolve({ status: 'ok', version: '0.1.0' }),
        }),
      ),
    )
    render(<SettingsMenu />)

    fireEvent.click(screen.getByRole('button', { name: 'Ajustes' }))

    expect(await screen.findByText('Versión v0.1.0')).toBeTruthy()
  })
})
