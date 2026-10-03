import { getLang } from '../i18n/i18n'

const UNITS = ['B', 'kB', 'MB', 'GB', 'TB'] as const

/** Tamaño legible en unidades decimales: 1,6 GB en español, 1.6 GB en inglés. */
export function formatBytes(bytes: number): string {
  let value = Math.max(0, bytes)
  let unit = 0
  while (value >= 1000 && unit < UNITS.length - 1) {
    value /= 1000
    unit += 1
  }
  // MB o menos: sin decimales; GB o más: un decimal (sin ",0").
  const decimals = unit >= 3 && value < 100 ? 1 : 0
  const separator = getLang() === 'es' ? ',' : '.'
  const text = value.toFixed(decimals).replace('.', separator).replace(/[.,]0$/, '')
  return text + '\u00a0' + UNITS[unit]
}
