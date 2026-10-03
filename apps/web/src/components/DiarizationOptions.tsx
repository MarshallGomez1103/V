import { useId, useState } from 'react'
import { Button, ContentSwitcher, NumberInput, ProgressBar, Switch, Toggle } from '@carbon/react'
import { CheckmarkOutline, Download } from '@carbon/icons-react'

import type { DiarizationModelState } from '../hooks/useDiarizationModel'
import { useI18n, type Translate } from '../i18n/i18n'
import { formatBytes } from '../lib/formatBytes'
import { InfoTip } from './Hint'
import { Busy } from './Busy'
import { Notice } from './Notice'
import './DiarizationOptions.scss'

export type DiarizationRequest = {
  enabled: boolean
  speakers: { exact?: number; minimum?: number; maximum?: number }
}

interface DiarizationOptionsProps {
  value: DiarizationRequest
  onChange: (value: DiarizationRequest) => void
  disabled?: boolean
  /** Estado del modelo de hablantes; sin él no se muestra el bloque de descarga. */
  model?: DiarizationModelState
}

type Mode = 'auto' | 'exact' | 'range'

const MODES: readonly Mode[] = ['auto', 'exact', 'range']
const MAX_SPEAKERS = 20

function modeOf(speakers: DiarizationRequest['speakers']): Mode {
  if (speakers.exact !== undefined) {
    return 'exact'
  }
  return speakers.minimum !== undefined || speakers.maximum !== undefined
    ? 'range'
    : 'auto'
}

/** Entero positivo o `undefined` si el campo está vacío o no es válido. */
function parseCount(text: string): number | undefined {
  const parsed = Number.parseInt(text, 10)
  return Number.isInteger(parsed) && parsed >= 1
    ? Math.min(parsed, MAX_SPEAKERS)
    : undefined
}

function ModelBlock({ model, t }: { model: DiarizationModelState; t: Translate }) {
  const size = model.model === null ? '' : formatBytes(model.model.size_bytes)
  const { task } = model

  switch (model.status) {
    case 'checking':
      return (
        <div role="status">
          <Busy description={t('diar.model.checking')} />
        </div>
      )
    case 'ready':
      return (
        <p className="voz-diarization__ready" role="status">
          <CheckmarkOutline size={16} aria-hidden="true" />
          {t('diar.model.ready')}
        </p>
      )
    case 'downloading': {
      const percent =
        task !== null && task.total_bytes > 0
          ? Math.min(100, Math.floor((task.done_bytes / task.total_bytes) * 100))
          : null
      return (
        <div className="voz-diarization__download" role="status">
          <ProgressBar
            size="small"
            label={t('diar.model.downloading.label')}
            helperText={
              task === null || task.state === 'queued' || percent === null
                ? t('diar.model.queued')
                : t('diar.model.downloading', {
                    pct: percent,
                    done: formatBytes(task.done_bytes),
                    total: formatBytes(task.total_bytes),
                  })
            }
            {...(task !== null && percent !== null
              ? { value: task.done_bytes, max: task.total_bytes }
              : {})}
          />
          <Button kind="ghost" size="sm" onClick={model.cancel}>
            {t('common.cancel')}
          </Button>
        </div>
      )
    }
    case 'missing':
      return (
        <div className="voz-diarization__missing">
          <Notice
            kind="warning"
            role="status"
            title={t('diar.model.missing.title')}
            subtitle={t('diar.model.missing.body', { size })}
          />
          {model.error !== null ? (
            <Notice kind="error" role="alert" title={model.error} />
          ) : null}
          <Button kind="tertiary" size="md" renderIcon={Download} onClick={model.download}>
            {t('diar.model.download', { size })}
          </Button>
        </div>
      )
    case 'unavailable':
      return (
        <Notice
          kind="error"
          role="status"
          title={t('diar.model.unavailable.title')}
          subtitle={t('diar.model.unavailable.body')}
        />
      )
    case 'error':
      return (
        <Notice
          kind="error"
          title={t('diar.model.error.title')}
          {...(model.error === null ? {} : { subtitle: model.error })}
          action={{ label: t('common.retry'), onClick: model.retry }}
        />
      )
    case 'off':
      return null
  }
}

export function DiarizationOptions({
  value,
  onChange,
  disabled = false,
  model,
}: DiarizationOptionsProps) {
  const { t } = useI18n()
  const name = useId()
  const [mode, setMode] = useState<Mode>(() => modeOf(value.speakers))
  const { exact, minimum, maximum } = value.speakers

  function choose(next: Mode) {
    setMode(next)
    onChange({
      ...value,
      speakers:
        next === 'exact'
          ? { exact: 2 }
          : next === 'range'
            ? { minimum: 1, maximum: 4 }
            : {},
    })
  }

  function setSpeakers(speakers: DiarizationRequest['speakers']) {
    onChange({ ...value, speakers })
  }

  const countProps = {
    translateWithId: (id: string) =>
      id === 'increment.number' ? t('diar.increase') : t('diar.decrease'),
    min: 1,
    max: MAX_SPEAKERS,
    size: 'md' as const,
    allowEmpty: true,
    disabled,
  }

  return (
    <div className="voz-diarization">
      <div className="voz-diarization__head">
        <Toggle
          id={name + '-enabled'}
          labelText={t('diar.toggle')}
          labelA={t('diar.off')}
          labelB={t('diar.on')}
          size="sm"
          toggled={value.enabled}
          disabled={disabled}
          onToggle={(checked) => {
            onChange({ ...value, enabled: checked })
          }}
        />
        <InfoTip label="diar.help.label">
          <p>{t('diar.help.1')}</p>
          <p>{t('diar.help.2')}</p>
        </InfoTip>
      </div>
      {value.enabled && model ? <ModelBlock model={model} t={t} /> : null}
      {value.enabled ? (
        <div className="voz-diarization__mode">
          <span className="cds--label" id={name + '-count'}>
            {t('diar.count')}
          </span>
          <ContentSwitcher
            size="md"
            aria-labelledby={name + '-count'}
            selectedIndex={MODES.indexOf(mode)}
            onChange={({ name: next }) => {
              if (!disabled) {
                choose(next as Mode)
              }
            }}
          >
            {MODES.map((item) => (
              <Switch key={item} name={item} text={t(`diar.mode.${item}`)} disabled={disabled} />
            ))}
          </ContentSwitcher>
          <p className="voz-field-note">{t(`diar.mode.${mode}.hint`)}</p>
          {mode === 'exact' ? (
            <NumberInput
              {...countProps}
              id={name + '-count-exact'}
              label={t('diar.exact.label')}
              value={exact ?? ''}
              onChange={(_event, state) => {
                const count = parseCount(String(state.value))
                setSpeakers(count === undefined ? {} : { exact: count })
              }}
            />
          ) : null}
          {mode === 'range' ? (
            <div className="voz-diarization__range">
              <NumberInput
                {...countProps}
                id={name + '-min'}
                label={t('diar.min')}
                value={minimum ?? ''}
                onChange={(_event, state) => {
                  const count = parseCount(String(state.value))
                  // Nunca se emite un rango invertido: el máximo sube con el mínimo.
                  setSpeakers({
                    ...(count === undefined ? {} : { minimum: count }),
                    ...(maximum === undefined
                      ? {}
                      : { maximum: Math.max(maximum, count ?? 0) }),
                  })
                }}
              />
              <NumberInput
                {...countProps}
                id={name + '-max'}
                label={t('diar.max')}
                value={maximum ?? ''}
                onChange={(_event, state) => {
                  const count = parseCount(String(state.value))
                  // Nunca se emite un rango invertido: el mínimo baja con el máximo.
                  setSpeakers({
                    ...(minimum === undefined
                      ? {}
                      : { minimum: Math.min(minimum, count ?? minimum) }),
                    ...(count === undefined ? {} : { maximum: count }),
                  })
                }}
              />
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
