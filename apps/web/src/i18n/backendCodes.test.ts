import { afterEach, describe, expect, it } from 'vitest'

import { failureMessage } from '../lib/jobFailure'
import { messageForSpeakerCode } from '../api/speakers'
import { setLang, translateCode } from './i18n'

afterEach(() => {
  setLang('es')
})

const NORMALIZATION_CODES = [
  'media_normalization_tool_unavailable',
  'media_normalization_invalid_source',
  'media_normalization_unsafe_destination',
  'media_normalization_destination_exists',
  'media_normalization_process_failed',
  'media_normalization_corrupted_media',
  'media_normalization_cancelled',
  'media_normalization_io_error',
]

describe('códigos del backend con mensaje propio', () => {
  it.each(NORMALIZATION_CODES)('el trabajo fallido con %s tiene mensaje distinto en es y en', (code) => {
    setLang('es')
    const es = failureMessage(code)
    setLang('en')
    const en = failureMessage(code)
    for (const message of [es, en]) {
      expect(message).not.toContain(code)
      expect(message).not.toMatch(/\(código|\(code/)
    }
    expect(en).not.toBe(es)
  })

  it('un código desconocido sigue mostrando el mensaje genérico con su código', () => {
    expect(failureMessage('gpu_lost')).toBe('La transcripción falló (código gpu_lost).')
  })

  it.each(['rediarize_unavailable', 'diarization_unavailable'])(
    'el recálculo de hablantes traduce %s sin caer en el genérico',
    (code) => {
      for (const lang of ['es', 'en'] as const) {
        setLang(lang)
        const message = messageForSpeakerCode(code)
        expect(message, lang).not.toContain(code)
        expect(message, lang).not.toMatch(/\(código|\(code/)
      }
    },
  )

  it('un trabajo inexistente al abrirlo tiene mensaje propio', () => {
    setLang('en')
    expect(translateCode('err.job.', 'job_not_found', 'err.job.generic')).not.toMatch(/code/)
  })
})
