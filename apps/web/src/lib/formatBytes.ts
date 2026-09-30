const UNITS = ['B', 'kB', 'MB', 'GB', 'TB'] as const

/** Tamaño legible en unidades decimales con coma decimal: 1,6 GB, 77 MB. */
export function formatBytes(bytes: number): string {
  let value = Math.max(0, bytes)
  let unit = 0
  while (value >= 1000 && unit < UNITS.length - 1) {
    value /= 1000
    unit += 1
  }
  // MB o menos: sin decimales; GB o más: un decimal (sin ",0").
  const decimals = unit >= 3 && value < 100 ? 1 : 0
  const text = value.toFixed(decimals).replace('.', ',').replace(/,0$/, '')
  return text + ' ' + UNITS[unit]
}
