import { useId, useState } from 'react'

import './DiarizationOptions.css'

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

  return (
    <fieldset className="diarization-options" disabled={disabled}>
      <legend className="diarization-options-legend">Hablantes</legend>
      <label className="diarization-options-toggle">
        <input
          type="checkbox"
          checked={value.enabled}
          onChange={(event) => {
            onChange({ ...value, enabled: event.target.checked })
          }}
        />
        Detectar quién habla
      </label>
      {value.enabled && (
        <div className="diarization-options-mode">
          <label>
            <input
              type="radio"
              name={name}
              checked={mode === 'auto'}
              onChange={() => {
                choose('auto')
              }}
            />
            Automático
          </label>
          <label>
            <input
              type="radio"
              name={name}
              checked={mode === 'exact'}
              onChange={() => {
                choose('exact')
              }}
            />
            Exacto
          </label>
          {mode === 'exact' && (
            <label>
              Número de hablantes
              <input
                type="number"
                min={1}
                max={MAX_SPEAKERS}
                value={exact ?? ''}
                onChange={(event) => {
                  const count = parseCount(event.target.value)
                  setSpeakers(count === undefined ? {} : { exact: count })
                }}
              />
            </label>
          )}
          <label>
            <input
              type="radio"
              name={name}
              checked={mode === 'range'}
              onChange={() => {
                choose('range')
              }}
            />
            Rango
          </label>
          {mode === 'range' && (
            <>
              <label>
                Mínimo
                <input
                  type="number"
                  min={1}
                  max={MAX_SPEAKERS}
                  value={minimum ?? ''}
                  onChange={(event) => {
                    const count = parseCount(event.target.value)
                    // Nunca se emite un rango invertido: el máximo sube con el mínimo.
                    setSpeakers({
                      ...(count === undefined ? {} : { minimum: count }),
                      ...(maximum === undefined
                        ? {}
                        : { maximum: Math.max(maximum, count ?? 0) }),
                    })
                  }}
                />
              </label>
              <label>
                Máximo
                <input
                  type="number"
                  min={1}
                  max={MAX_SPEAKERS}
                  value={maximum ?? ''}
                  onChange={(event) => {
                    const count = parseCount(event.target.value)
                    // Nunca se emite un rango invertido: el mínimo baja con el máximo.
                    setSpeakers({
                      ...(minimum === undefined
                        ? {}
                        : { minimum: Math.min(minimum, count ?? minimum) }),
                      ...(count === undefined ? {} : { maximum: count }),
                    })
                  }}
                />
              </label>
            </>
          )}
        </div>
      )}
    </fieldset>
  )
}
