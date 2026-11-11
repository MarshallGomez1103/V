import { useId, type CSSProperties, type KeyboardEvent } from 'react'
import { Button } from '@carbon/react'

import { useI18n } from '../i18n/i18n'
import {
  formatTrimTime,
  TRIM_STEP_MS,
  trimSummary,
  validateTrim,
  type TrimRange,
} from '../lib/trimRange'
import { Notice } from './Notice'
import { Panel } from './Panel'
import './TrimControls.scss'

interface TrimControlsProps {
  /** Duración que el servidor midió al importar; `null` = no se puede recortar. */
  durationMs: number | null
  /** Tramo elegido; `null` = grabación completa. */
  value: TrimRange | null
  /** Posición actual del reproductor, para «Inicio aquí» y «Fin aquí». */
  currentMs: number
  onChange: (range: TrimRange | null) => void
  /** Reproduce desde `ms` y se detiene en `stopAtMs`. */
  onSeek: (ms: number, stopAtMs?: number) => void
  disabled?: boolean
}

function fill(ms: number, durationMs: number): CSSProperties {
  return { '--voz-fill': String(durationMs > 0 ? (ms / durationMs) * 100 : 0) + '%' } as CSSProperties
}

/** Inicio y fin del tramo a transcribir: deslizadores nativos con paso de 100 ms. */
export function TrimControls({
  durationMs,
  value,
  currentMs,
  onChange,
  onSeek,
  disabled = false,
}: TrimControlsProps) {
  const { t } = useI18n()
  const id = useId()
  const known = durationMs !== null
  const total = durationMs ?? 0
  const range = value ?? { startMs: 0, endMs: total }
  const error = known && value !== null ? validateTrim(range.startMs, range.endMs, total) : null
  const off = disabled || !known

  // Un tramo que cubre toda la grabación vuelve a ser «sin recorte».
  const emit = (startMs: number, endMs: number) => {
    onChange(startMs <= 0 && endMs >= total ? null : { startMs, endMs })
  }
  // El range nativo no llega a un `max` que no sea múltiplo del paso: el último paso vale «hasta el final».
  const snap = (ms: number) =>
    ms >= total - TRIM_STEP_MS / 2 ? total : Math.min(total, Math.max(0, Math.round(ms / TRIM_STEP_MS) * TRIM_STEP_MS))
  const arrows = (current: number, set: (ms: number) => void) => (event: KeyboardEvent<HTMLInputElement>) => {
    const sign =
      event.key === 'ArrowRight' || event.key === 'ArrowUp' ? 1
        : event.key === 'ArrowLeft' || event.key === 'ArrowDown' ? -1
          : 0
    if (sign !== 0) {
      event.preventDefault()
      set(snap(current + sign * TRIM_STEP_MS))
    }
  }

  const slider = (key: 'start' | 'end', ms: number, set: (ms: number) => void) => (
    <div className="voz-trim__field">
      <label htmlFor={id + key}>{t(key === 'start' ? 'trim.start' : 'trim.end')}</label>
      <input
        id={id + key}
        type="range"
        className="voz-range voz-trim__slider"
        min={0}
        max={total}
        step={TRIM_STEP_MS}
        value={ms}
        disabled={off}
        style={fill(ms, total)}
        aria-valuetext={formatTrimTime(ms)}
        onChange={(event) => {
          set(snap(Number(event.currentTarget.value)))
        }}
        onKeyDown={arrows(ms, set)}
      />
      <output htmlFor={id + key} className="voz-trim__time">
        {formatTrimTime(ms)}
      </output>
    </div>
  )

  return (
    <Panel titleId={id + 'title'} title={t('trim.title')} description={t('trim.description')}>
      <div className="voz-trim">
        {!known ? <Notice kind="warning" title={t('trim.unknownDuration')} /> : null}
        {slider('start', range.startMs, (ms) => { emit(ms, range.endMs) })}
        {slider('end', range.endMs, (ms) => { emit(range.startMs, ms) })}
        <div className="voz-trim__actions">
          <Button
            kind="tertiary"
            size="sm"
            disabled={off}
            onClick={() => { emit(snap(currentMs), range.endMs) }}
          >
            {t('trim.startHere')}
          </Button>
          <Button
            kind="tertiary"
            size="sm"
            disabled={off}
            onClick={() => { emit(range.startMs, snap(currentMs)) }}
          >
            {t('trim.endHere')}
          </Button>
          <Button
            kind="tertiary"
            size="sm"
            disabled={off || error !== null}
            onClick={() => { onSeek(range.startMs, range.endMs) }}
          >
            {t('trim.play')}
          </Button>
          <Button
            kind="ghost"
            size="sm"
            disabled={off || value === null}
            onClick={() => { onChange(null) }}
          >
            {t('trim.clear')}
          </Button>
        </div>
        {error !== null ? (
          <Notice kind="error" title={t(`trim.error.${error}`)} />
        ) : known ? (
          <p className="voz-field-note" role="status">
            {value === null ? t('trim.whole') : t('trim.summary', trimSummary(range.startMs, range.endMs, total))}
          </p>
        ) : null}
      </div>
    </Panel>
  )
}
