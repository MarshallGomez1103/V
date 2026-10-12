import { useEffect, useId, useState } from 'react'
import { Button, Column, Grid, Select, SelectItem, TextArea } from '@carbon/react'
import { ArrowRight } from '@carbon/icons-react'

import { isAbortError } from '../api/errors'
import {
  getSynthesisOptions,
  SynthesisApiError,
  type SynthesisOptions,
} from '../api/synthesis'
import { localeOf, translate, useI18n } from '../i18n/i18n'
import { speakTextStatus } from '../lib/speakText'
import { Busy } from './Busy'
import { Notice } from './Notice'
import { Panel } from './Panel'
import './SpeakWorkspace.scss'

type LoadState =
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; options: SynthesisOptions }

interface SpeakWorkspaceProps {
  /** Cambia cuando se instala o borra un modelo: las opciones se vuelven a pedir. */
  modelsVersion?: number
  onOpenModels: () => void
}

function loadErrorMessage(error: unknown): string {
  return error instanceof SynthesisApiError ? error.message : translate('speak.error.title')
}

/** Texto a voz: carga las opciones de la API y, según haya voces, muestra el editor o la invitación a Modelos. */
export function SpeakWorkspace({ modelsVersion = 0, onOpenModels }: SpeakWorkspaceProps) {
  const { t } = useI18n()
  const [state, setState] = useState<LoadState>({ phase: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [text, setText] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    void getSynthesisOptions(controller.signal)
      .then((options) => {
        setState({ phase: 'ready', options })
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          setState({ phase: 'error', message: loadErrorMessage(error) })
        }
      })
    return () => {
      controller.abort()
    }
  }, [attempt, modelsVersion])

  if (state.phase === 'loading') {
    return (
      <div className="voz-speak">
        <Busy description={t('speak.loading')} />
      </div>
    )
  }
  if (state.phase === 'error') {
    return (
      <div className="voz-speak">
        <Notice
          kind="error"
          title={t('speak.error.title')}
          subtitle={state.message}
          action={{
            label: t('common.retry'),
            onClick: () => {
              setState({ phase: 'loading' })
              setAttempt((current) => current + 1)
            },
          }}
        />
      </div>
    )
  }
  if (state.options.models.length === 0) {
    return (
      <div className="voz-speak">
        <Panel titleId="voz-speak-empty" title={t('speak.empty.title')} className="voz-speak__empty">
          <p className="voz-speak__empty-body">{t('speak.empty.body')}</p>
          <div>
            <Button kind="primary" size="md" renderIcon={ArrowRight} onClick={onOpenModels}>
              {t('speak.empty.action')}
            </Button>
          </div>
        </Panel>
      </div>
    )
  }
  return <SpeakEditor options={state.options} text={text} onText={setText} />
}

interface SpeakEditorProps {
  options: SynthesisOptions
  text: string
  onText: (text: string) => void
}

function SpeakEditor({ options, text, onText }: SpeakEditorProps) {
  const { t, tn, lang } = useI18n()
  const id = useId()
  const format = new Intl.NumberFormat(localeOf(lang))
  const status = speakTextStatus(text, options.max_chars)
  const voices = options.models.reduce((total, model) => total + model.voices.length, 0)
  const near = status.level === 'near'
  const over = status.level === 'over'
  return (
    <Grid narrow className="voz-grid voz-speak">
      <Column sm={4} md={5} lg={10}>
        <Panel titleId={id + '-text'} title={t('speak.text.title')}>
          <TextArea
            id={id + '-area'}
            labelText={t('speak.text.label')}
            hideLabel
            placeholder={t('speak.text.placeholder')}
            rows={14}
            value={text}
            invalid={over}
            invalidText={t('speak.over', { over: format.format(status.over) })}
            warn={near}
            warnText={t('speak.warn.near', { left: format.format(status.left) })}
            onChange={(event) => {
              onText(event.target.value)
            }}
          />
          <div className="voz-speak__footer">
            <p
              className={'voz-speak__counter' + (over ? ' voz-speak__counter--over' : '')}
              data-testid="speak-counter"
            >
              {t('speak.counter', {
                chars: format.format(status.chars),
                max: format.format(options.max_chars),
              })}
              {' · '}
              {tn('speak.counter.words', status.words, { n: format.format(status.words) })}
            </p>
            <Button
              kind="ghost"
              size="sm"
              disabled={text === ''}
              onClick={() => {
                onText('')
              }}
            >
              {t('speak.clear')}
            </Button>
          </div>
        </Panel>
      </Column>
      <Column sm={4} md={3} lg={6}>
        <Panel
          titleId={id + '-voice'}
          title={t('speak.voice.title')}
          description={t('speak.voice.description', {
            models: options.models.length,
            voices,
          })}
          className="voz-speak__voice"
        >
          {/* Marcador de V5-02: los selectores reales sustituyen a estos campos. */}
          <div className="voz-speak__placeholder" data-testid="speak-selectors-placeholder">
            <Select id={id + '-model'} labelText={t('speak.voice.model')} disabled>
              <SelectItem value="" text="—" />
            </Select>
            <Select id={id + '-voice-select'} labelText={t('speak.voice.voice')} disabled>
              <SelectItem value="" text="—" />
            </Select>
            <Select id={id + '-language'} labelText={t('speak.voice.language')} disabled>
              <SelectItem value="" text="—" />
            </Select>
            <p className="voz-field-note">{t('speak.voice.soon')}</p>
          </div>
        </Panel>
      </Column>
    </Grid>
  )
}
