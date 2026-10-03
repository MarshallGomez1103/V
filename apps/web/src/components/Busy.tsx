import { InlineLoading } from '@carbon/react'

/** Indicador de carga en línea con la descripción accesible en español. */
export function Busy({ description }: { description: string }) {
  return <InlineLoading description={description} iconDescription="Cargando" />
}
