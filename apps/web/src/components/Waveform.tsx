import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
} from 'react'
import { IconButton } from '@carbon/react'
import { ZoomIn, ZoomOut } from '@carbon/icons-react'

import {
  getWaveformPeaks,
  WaveformApiError,
  type WaveformPeaks,
} from '../api/waveform'
import {
  clampZoom,
  columnPeaks,
  contentWidth,
  isVisibleX,
  MAX_ZOOM,
  MIN_ZOOM,
  msToX,
  scrollLeftForZoom,
  scrollLeftToReveal,
  seekTarget,
  xToMs,
  zoomIn,
  zoomOut,
} from '../lib/waveformGeometry'
import { isAbortError } from '../api/errors'
import { formatSeconds } from '../lib/formatTime'
import { useI18n } from '../i18n/i18n'
import { Busy } from './Busy'
import { Notice } from './Notice'
import './Waveform.scss'

export interface WaveformProps {
  mediaAssetId: string
  currentMs: number
  onSeek: (ms: number) => void
  /** Duración total medida por el backend (sirve para grabaciones abiertas desde «guardadas»). */
  onDuration?: ((ms: number) => void) | undefined
}

// Más buckets que el valor por defecto del backend (2000) para que el zoom alto
// siga teniendo detalle; el backend lo cachea por (audio, buckets).
const PEAK_BUCKETS = 4000
// jsdom y los primeros renders no miden ancho: valor de reserva.
const FALLBACK_VIEWPORT_WIDTH = 640
const CANVAS_HEIGHT = 96

type Outcome =
  | { phase: 'error'; message: string | null }
  | { phase: 'ready'; data: WaveformPeaks }

interface Loaded {
  mediaAssetId: string
  outcome: Outcome
}

function drawColumns(
  canvas: HTMLCanvasElement,
  columns: readonly (readonly [number, number])[],
  width: number,
): void {
  const context = canvas.getContext('2d')
  if (!context) {
    return // jsdom y navegadores sin canvas: el waveform queda sin dibujar.
  }
  const ratio = Math.max(1, window.devicePixelRatio || 1)
  const pixelWidth = Math.round(width * ratio)
  const pixelHeight = Math.round(CANVAS_HEIGHT * ratio)
  if (canvas.width !== pixelWidth) {
    canvas.width = pixelWidth
  }
  if (canvas.height !== pixelHeight) {
    canvas.height = pixelHeight
  }
  context.setTransform(ratio, 0, 0, ratio, 0, 0)
  context.clearRect(0, 0, width, CANVAS_HEIGHT)
  // Color del tema (token Carbon vía CSS); sin estilos calculados, el del texto.
  context.fillStyle = window.getComputedStyle(canvas).color || 'currentColor'
  const middle = CANVAS_HEIGHT / 2
  columns.forEach(([low, high], x) => {
    // Al menos 1 px para que el silencio siga viéndose como una línea.
    const top = middle - high * middle
    const bottom = middle - low * middle
    context.fillRect(x, top, 1, Math.max(1, bottom - top))
  })
}

// S5.09: canvas con peaks precalculados; S5.14: zoom 1x-32x con scroll
// horizontal. El canvas mide solo la vista (sticky) y dibuja la porción
// visible: así el zoom alto no choca con el límite de tamaño de los canvas.
export function Waveform({ mediaAssetId, currentMs, onSeek, onDuration }: WaveformProps) {
  const durationRef = useRef(onDuration)
  useEffect(() => {
    durationRef.current = onDuration
  })
  const { t } = useI18n()
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [zoom, setZoom] = useState(MIN_ZOOM)
  const [viewportWidth, setViewportWidth] = useState(0)
  const scrollerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const following = useRef(true)
  const pendingScroll = useRef<number | null>(null)

  const outcome = loaded?.mediaAssetId === mediaAssetId ? loaded.outcome : null
  const data = outcome?.phase === 'ready' ? outcome.data : null
  const width = viewportWidth > 0 ? viewportWidth : FALLBACK_VIEWPORT_WIDTH
  const totalWidth = contentWidth(width, zoom)
  const durationMs = data?.duration_ms ?? 0

  useEffect(() => {
    const controller = new AbortController()
    getWaveformPeaks(mediaAssetId, {
      buckets: PEAK_BUCKETS,
      signal: controller.signal,
    })
      .then((result) => {
        setLoaded({ mediaAssetId, outcome: { phase: 'ready', data: result } })
        durationRef.current?.(result.duration_ms)
      })
      .catch((error: unknown) => {
        if (isAbortError(error) || controller.signal.aborted) {
          return
        }
        const message = error instanceof WaveformApiError ? error.message : null
        setLoaded({ mediaAssetId, outcome: { phase: 'error', message } })
      })
    return () => {
      controller.abort()
    }
  }, [mediaAssetId])

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    const scroller = scrollerRef.current
    if (!canvas || !scroller || !data) {
      return
    }
    const columns = columnPeaks(data.peaks, scroller.scrollLeft, width, totalWidth)
    drawColumns(canvas, columns, width)
  }, [data, width, totalWidth])

  useLayoutEffect(() => {
    const scroller = scrollerRef.current
    if (!scroller || typeof ResizeObserver === 'undefined') {
      return
    }
    const observer = new ResizeObserver(() => {
      setViewportWidth(scroller.clientWidth)
    })
    observer.observe(scroller)
    return () => {
      observer.disconnect()
    }
  }, [data])

  // Tras un cambio de zoom el ancho del contenido ya está en el DOM: aplica el
  // scroll que mantiene el playhead visible y redibuja.
  useLayoutEffect(() => {
    const scroller = scrollerRef.current
    if (scroller && pendingScroll.current !== null) {
      scroller.scrollLeft = pendingScroll.current
      pendingScroll.current = null
    }
    draw()
  }, [draw, zoom])

  // Sigue la reproducción solo mientras el usuario no se ha alejado a mano.
  useEffect(() => {
    const scroller = scrollerRef.current
    if (!scroller || durationMs <= 0) {
      return
    }
    const x = msToX(currentMs, durationMs, totalWidth)
    if (isVisibleX(x, scroller.scrollLeft, width)) {
      following.current = true
    } else if (following.current) {
      scroller.scrollLeft = scrollLeftToReveal(
        x,
        scroller.scrollLeft,
        width,
        totalWidth,
      )
      draw()
    }
  }, [currentMs, durationMs, totalWidth, width, draw])

  if (outcome === null) {
    return (
      <div className="waveform waveform--status" role="status">
        <Busy description={t('wave.loading')} />
      </div>
    )
  }
  if (outcome.phase === 'error') {
    return (
      <div className="waveform waveform--status">
        <Notice kind="error" title={outcome.message ?? t('err.wave.load')} />
      </div>
    )
  }

  const playheadX = msToX(currentMs, durationMs, totalWidth)

  const changeZoom = (next: number) => {
    const target = clampZoom(next)
    if (target === zoom) {
      return
    }
    const scroller = scrollerRef.current
    pendingScroll.current = scrollLeftForZoom({
      playheadMs: currentMs,
      durationMs,
      viewportWidth: width,
      oldZoom: zoom,
      newZoom: target,
      scrollLeft: scroller?.scrollLeft ?? 0,
    })
    following.current = true
    setZoom(target)
  }

  const handleScroll = () => {
    const scroller = scrollerRef.current
    if (scroller) {
      following.current = isVisibleX(playheadX, scroller.scrollLeft, width)
    }
    draw()
  }

  const handleClick = (event: MouseEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    onSeek(xToMs(event.clientX - rect.left, durationMs, totalWidth))
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') {
      return
    }
    event.preventDefault()
    onSeek(
      seekTarget(currentMs, event.key === 'ArrowLeft' ? -1 : 1, durationMs),
    )
  }

  const clock = t('wave.clock', { now: formatSeconds(currentMs / 1000), total: formatSeconds(durationMs / 1000) })

  return (
    <section className="waveform" aria-label={t('wave.region')}>
      <div className="waveform__toolbar">
        <IconButton
          kind="ghost"
          size="sm"
          label={t('wave.zoomOut')}
          onClick={() => {
            changeZoom(zoomOut(zoom))
          }}
          disabled={zoom <= MIN_ZOOM}
        >
          <ZoomOut />
        </IconButton>
        <input
          type="range"
          className="waveform__slider voz-range"
          min={MIN_ZOOM}
          max={MAX_ZOOM}
          step={1}
          value={zoom}
          style={{ '--voz-fill': String(((zoom - MIN_ZOOM) / (MAX_ZOOM - MIN_ZOOM)) * 100) + '%' } as React.CSSProperties}
          aria-label={t('wave.zoom')}
          aria-valuetext={t('wave.zoomValue', { zoom })}
          onChange={(event) => {
            changeZoom(Number(event.currentTarget.value))
          }}
        />
        <IconButton
          kind="ghost"
          size="sm"
          label={t('wave.zoomIn')}
          onClick={() => {
            changeZoom(zoomIn(zoom))
          }}
          disabled={zoom >= MAX_ZOOM}
        >
          <ZoomIn />
        </IconButton>
        <output className="waveform__zoom">{String(zoom) + 'x'}</output>
        <span className="waveform__clock">{clock}</span>
      </div>
      <div
        ref={scrollerRef}
        className="waveform__scroller"
        role="slider"
        tabIndex={0}
        aria-label={t('wave.slider')}
        aria-valuemin={0}
        aria-valuemax={durationMs}
        aria-valuenow={Math.round(Math.min(Math.max(currentMs, 0), durationMs))}
        aria-valuetext={clock}
        onScroll={handleScroll}
        onKeyDown={handleKeyDown}
      >
        <div
          className="waveform__content"
          style={{ width: totalWidth }}
          onClick={handleClick}
        >
          <canvas
            ref={canvasRef}
            className="waveform__canvas"
            aria-hidden="true"
            width={width}
            height={CANVAS_HEIGHT}
            style={{ width, height: CANVAS_HEIGHT }}
          />
          <div
            className="waveform__playhead"
            aria-hidden="true"
            style={{ left: playheadX }}
          />
        </div>
      </div>
    </section>
  )
}

