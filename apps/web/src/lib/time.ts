/** Fecha ISO del backend a ms; si no trae zona horaria se asume UTC. `null` si no es válida. */
export function parseIso(value: string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') {
    return null
  }
  const hasZone = /(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(value)
  const parsed = Date.parse(hasZone ? value : value + 'Z')
  return Number.isNaN(parsed) ? null : parsed
}
