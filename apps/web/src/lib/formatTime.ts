/** Reloj `m:ss` o `h:mm:ss` a partir de milisegundos (duración o posición). */
export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000))
  return formatSeconds(total)
}

/** Reloj `m:ss` / `h:mm:ss` a partir de segundos enteros. */
export function formatSeconds(totalSeconds: number): string {
  const total = Math.max(0, Math.floor(totalSeconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return hours > 0
    ? hours + ':' + pad(minutes) + ':' + pad(seconds)
    : String(minutes) + ':' + pad(seconds)
}

/** Marca de tiempo de transcripción: `mm:ss.d`. */
export function formatStamp(ms: number): string {
  const total = Math.max(0, ms)
  const minutes = Math.floor(total / 60_000)
  const seconds = Math.floor((total % 60_000) / 1000)
  const tenths = Math.floor((total % 1000) / 100)
  return (
    String(minutes).padStart(2, '0') +
    ':' +
    String(seconds).padStart(2, '0') +
    '.' +
    String(tenths)
  )
}
