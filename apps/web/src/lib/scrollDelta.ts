/** Desplazamiento vertical mínimo para que `row` quede visible en `container`. */
export function scrollDelta(
  container: { top: number; bottom: number },
  row: { top: number; bottom: number },
): number {
  if (row.top < container.top) {
    return row.top - container.top
  }
  if (row.bottom > container.bottom) {
    // Fila más alta que el contenedor: prioriza mostrar su inicio.
    return Math.min(
      row.bottom - container.bottom,
      row.top - container.top,
    )
  }
  return 0
}
