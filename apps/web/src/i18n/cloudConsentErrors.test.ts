import { afterEach, describe, expect, it } from 'vitest'

import { messageForSynthesisError } from '../api/synthesis'
import { setLang } from './i18n'

afterEach(() => {
  setLang('es')
})

describe('mensajes de consentimiento cloud', () => {
  it.each([
    ['es', 'cloud_consent_required', /confirma el permiso/i],
    ['en', 'cloud_consent_required', /confirm the permission/i],
    ['es', 'cloud_consent_expired', /se reinici/i],
    ['en', 'cloud_consent_expired', /restarted/i],
  ] as const)('%s · %s tiene texto propio, no el genérico', (lang, code, expected) => {
    setLang(lang)
    const message = messageForSynthesisError(code)
    expect(message).toMatch(expected)
    expect(message).not.toContain(code)
  })
})
