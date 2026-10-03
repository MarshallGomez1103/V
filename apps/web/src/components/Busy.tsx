import { InlineLoading } from '@carbon/react'

import { useI18n } from '../i18n/i18n'

/** Indicador de carga en línea con la descripción accesible en el idioma activo. */
export function Busy({ description }: { description: string }) {
  const { t } = useI18n()
  return <InlineLoading description={description} iconDescription={t('common.loading')} />
}
