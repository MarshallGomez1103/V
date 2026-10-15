import { useEffect, useId, useState } from 'react'
import { Button, Checkbox, Column, Grid, TextArea } from '@carbon/react'
import { ArrowRight, StopFilledAlt, VolumeUp } from '@carbon/icons-react'

import { isAbortError } from '../api/errors'
import {
  ACTIVE_SYNTHESIS_STATES,
  cancelSynthesis,
  createSynthesis,
  getSynthesisOptions,
  SynthesisApiError,
  type SynthesisOptions,
  type SynthesisView,
} from '../api/synthesis'
import { useSpeakSample } from '../hooks/useSpeakSample'
import { useSynthesisEvents } from '../hooks/useSynthesisEvents'
import { localeOf, translate, useI18n } from '../i18n/i18n'
import {
  firstSentence,
  loadPreference,
  modelKey,
  requestOf,
  resolveChoice,
  sampleLanguage,
  SAMPLE_MAX_CHARS,
  savePreference,
  type SpeakPreference,
} from '../lib/speakChoice'
import { speakTextStatus } from '../lib/speakText'
import { Busy } from './Busy'
import { Notice } from './Notice'
import { Panel } from './Panel'
import { SpeakResult } from './SpeakResult'
import { SpeakVoicePicker } from './SpeakVoicePicker'
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

interface Generation {
  id: string
  reused: boolean
  /** Respuesta de `POST`: se muestra mientras llega la primera instantánea del stream. */
  seed: SynthesisView
  voiceName: string
}

function SpeakEditor({ options, text, onText }: SpeakEditorProps) {
  const { t, tn, lang } = useI18n()
  const id = useId()
  const format = new Intl.NumberFormat(localeOf(lang))
  const status = speakTextStatus(text, options.max_chars)
  const voices = options.models.reduce((total, model) => total + model.voices.length, 0)
  const near = status.level === 'near'
  const over = status.level === 'over'

  // La elección se guarda cruda y se resuelve contra las opciones vigentes en cada render:
  // si Modelos borra el modelo elegido, cae solo en otro.
  const [preference, setPreference] = useState<SpeakPreference>(loadPreference)
  const choice = resolveChoice(options, preference, lang)
  const request = requestOf(choice)
  const cloud = options.providers.some(
    (provider) => provider.provider_id === choice.model.provider_id && provider.locality === 'cloud',
  )
  const [confirmedCloud, setConfirmedCloud] = useState<string | null>(null)
  const usable = request !== null && choice.model.runtime_ready &&
    (!cloud || confirmedCloud === modelKey(choice.model))
  const change = (next: SpeakPreference) => {
    setConfirmedCloud(null)
    setPreference(next)
    savePreference(resolveChoice(options, next, lang))
  }

  const [generation, setGeneration] = useState<Generation | null>(null)
  const [creating, setCreating] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const events = useSynthesisEvents(generation?.id ?? null)
  const job = events.job ?? generation?.seed ?? null
  const active = job !== null && ACTIVE_SYNTHESIS_STATES.has(job.state)

  const generate = () => {
    if (request === null || !usable || !status.canGenerate || creating || active) {
      return
    }
    setCreating(true)
    setProblem(null)
    const voiceName = choice.voice?.name ?? request.voice_id
    createSynthesis({ text, ...request })
      .then((created) => {
        setGeneration({ id: created.id, reused: created.reused, seed: created, voiceName })
      })
      .catch((cause: unknown) => {
        setProblem(cause instanceof SynthesisApiError ? cause.message : translate('speak.error.title'))
      })
      .finally(() => {
        setCreating(false)
      })
  }

  const cancel = () => {
    if (generation === null) {
      return
    }
    cancelSynthesis(generation.id).catch((cause: unknown) => {
      // 409: ya había terminado; el stream trae el estado final.
      if (!(cause instanceof SynthesisApiError && cause.status === 409)) {
        setProblem(cause instanceof SynthesisApiError ? cause.message : translate('speak.error.title'))
      }
    })
  }

  const sample = useSpeakSample()
  const sampleBusy = sample.phase !== 'idle'
  const listen = () => {
    if (sampleBusy) {
      sample.stop()
      return
    }
    if (request === null || !usable) {
      return
    }
    sample.start({
      ...request,
      text: firstSentence(text) || t(`speak.sample.text.${sampleLanguage(choice)}`),
    })
  }

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
          <SpeakVoicePicker
            id={id}
            options={options}
            choice={choice}
            disabled={creating || active}
            onChange={change}
          />
          {cloud ? (
            <Checkbox
              id={id + '-cloud-confirm'}
              labelText={t('speak.cloud.confirm')}
              checked={confirmedCloud === modelKey(choice.model)}
              disabled={creating || active}
              onChange={(_, { checked }) => {
                setConfirmedCloud(checked ? modelKey(choice.model) : null)
              }}
            />
          ) : null}
          <div className="voz-speak__actions">
            <Button
              kind="tertiary"
              size="md"
              renderIcon={sampleBusy ? StopFilledAlt : VolumeUp}
              disabled={!usable && !sampleBusy}
              onClick={listen}
            >
              {sample.phase === 'playing'
                ? t('speak.sample.stop')
                : sample.phase === 'preparing'
                  ? t('speak.sample.cancel')
                  : t('speak.sample')}
            </Button>
            <Button
              kind="primary"
              size="md"
              disabled={!usable || !status.canGenerate || creating || active}
              onClick={generate}
            >
              {creating ? t('speak.generate.creating') : t('speak.generate')}
            </Button>
          </div>
          <p className="cds--visually-hidden" role="status">
            {sample.phase === 'preparing'
              ? t('speak.sample.preparing')
              : sample.phase === 'playing'
                ? t('speak.sample.playing')
                : ''}
          </p>
          <p className="voz-field-note">
            {status.chars === 0 ? t('speak.generate.needText') + ' ' : ''}
            {t('speak.sample.hint', { max: SAMPLE_MAX_CHARS })}
          </p>
          {sample.error !== null ? (
            <Notice kind="error" title={t('speak.sample.failed')} subtitle={sample.error} />
          ) : null}
          {problem !== null ? <Notice kind="error" title={t('speak.error.title')} subtitle={problem} /> : null}
        </Panel>
      </Column>
      {generation !== null || creating ? (
        <Column sm={4} md={8} lg={16}>
          <SpeakResult
            job={generation === null ? null : job}
            reused={generation?.reused ?? false}
            voiceName={generation?.voiceName ?? ''}
            locality={options.providers.find(
              (provider) => provider.provider_id === (job?.provider_id ?? choice.model.provider_id),
            )?.locality ?? 'local'}
            streamError={events.error}
            onCancel={cancel}
            onReconnect={events.retry}
          />
        </Column>
      ) : null}
    </Grid>
  )
}
