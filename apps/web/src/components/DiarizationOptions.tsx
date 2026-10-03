import { useId, useState } from 'react'
import { NumberInput, RadioButton, RadioButtonGroup, Toggle } from '@carbon/react'

import './DiarizationOptions.scss'

export type DiarizationRequest = {
  enabled: boolean
  speakers: { exact?: number; minimum?: number; maximum?: number }
}

interface DiarizationOptionsProps {
  value: DiarizationRequest
  onChange: (value: DiarizationRequest) => void
  disabled?: boolean
}

type Mode = 'auto' | 'exact' | 'range'

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

export function DiarizationOptions({
  value,
  onChange,
  disabled = false,
}: DiarizationOptionsProps) {
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
      id === 'increment.number' ? 'Aumentar el número' : 'Disminuir el número',
    min: 1,
    max: MAX_SPEAKERS,
    size: 'md' as const,
    allowEmpty: true,
    disabled,
  }

  return (
    <div className="voz-diarization">
      <Toggle
        id={name + '-enabled'}
        labelText="Detectar quién habla"
        labelA="Desactivado"
        labelB="Activado"
        size="sm"
        toggled={value.enabled}
        disabled={disabled}
        onToggle={(checked) => {
          onChange({ ...value, enabled: checked })
        }}
      />
      {value.enabled ? (
        <div className="voz-diarization__mode">
          <RadioButtonGroup
            legendText="Cantidad de hablantes"
            name={name}
            orientation="horizontal"
            valueSelected={mode}
            disabled={disabled}
            onChange={(next) => {
              choose(next as Mode)
            }}
          >
            <RadioButton id={name + '-auto'} value="auto" labelText="Automático" />
            <RadioButton id={name + '-exact'} value="exact" labelText="Exacto" />
            <RadioButton id={name + '-range'} value="range" labelText="Rango" />
          </RadioButtonGroup>
          {mode === 'exact' ? (
            <NumberInput
              {...countProps}
              id={name + '-count'}
              label="Número de hablantes"
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
                label="Mínimo"
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
                label="Máximo"
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
