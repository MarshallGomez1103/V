import { useId } from 'react'
import { Button, TextArea } from '@carbon/react'

import { useI18n } from '../i18n/i18n'
import { InfoTip } from './Hint'
import './StyleInstructions.scss'

export const PROMPT_MAX_LENGTH = 600

interface StyleInstructionsProps {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
}

/**
 * Texto de contexto para el motor («prompt» de Whisper). No es una orden: Whisper imita
 * el estilo del texto de ejemplo, así que la ayuda lo dice con honestidad.
 */
export function StyleInstructions({ value, onChange, disabled = false }: StyleInstructionsProps) {
  const { t } = useI18n()
  const id = useId()
  return (
    <div className="voz-style">
      <div className="voz-style__head">
        <label className="cds--label" htmlFor={id}>
          {t('style.label')}
        </label>
        <InfoTip label="style.help.label" align="bottom-end">
          <p>{t('style.help.1')}</p>
          <p>{t('style.help.2')}</p>
          <p>{t('style.help.3')}</p>
        </InfoTip>
      </div>
      <TextArea
        id={id}
        labelText={t('style.label')}
        hideLabel
        rows={4}
        value={value}
        maxCount={PROMPT_MAX_LENGTH}
        enableCounter
        disabled={disabled}
        placeholder={t('style.placeholder')}
        helperText={t('style.helper')}
        onChange={(event) => {
          onChange(event.target.value.slice(0, PROMPT_MAX_LENGTH))
        }}
      />
      <div className="voz-style__actions">
        <Button
          kind="ghost"
          size="sm"
          disabled={disabled || value === t('style.example')}
          onClick={() => {
            onChange(t('style.example'))
          }}
        >
          {t('style.useExample')}
        </Button>
        {value !== '' ? (
          <Button
            kind="ghost"
            size="sm"
            disabled={disabled}
            onClick={() => {
              onChange('')
            }}
          >
            {t('style.clear')}
          </Button>
        ) : null}
      </div>
    </div>
  )
}
