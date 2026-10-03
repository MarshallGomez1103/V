import type { ReactNode } from 'react'
import { DefinitionTooltip, Toggletip, ToggletipButton, ToggletipContent } from '@carbon/react'
import { Information } from '@carbon/icons-react'

import { useI18n } from '../i18n/i18n'
import type { MessageKey } from '../i18n/messages'
import './Hint.scss'

interface TermProps {
  /** Texto visible (término técnico). */
  children: ReactNode
  /** Explicación breve que sale al pasar el ratón o enfocar. */
  definition: MessageKey
  /**
   * Dentro de controles que no admiten contenido interactivo (opciones de radio, fichas
   * seleccionables): la definición va en el atributo `title` en lugar de un botón.
   */
  plain?: boolean
}

/** Término técnico con su definición en un tooltip (subrayado punteado, enfocable). */
export function Term({ children, definition, plain = false }: TermProps) {
  const { t } = useI18n()
  if (plain) {
    return (
      <span className="voz-term" title={t(definition)}>
        {children}
      </span>
    )
  }
  return (
    <DefinitionTooltip definition={t(definition)} openOnHover>
      {children}
    </DefinitionTooltip>
  )
}

interface InfoTipProps {
  /** Nombre accesible del botón (p. ej. «Cómo funciona»). */
  label: MessageKey
  children: ReactNode
  align?: 'top' | 'bottom' | 'top-start' | 'bottom-start' | 'top-end' | 'bottom-end'
}

/** Botón «i» que abre una explicación más larga (Toggletip: se queda hasta cerrarlo). */
export function InfoTip({ label, children, align = 'bottom-start' }: InfoTipProps) {
  const { t } = useI18n()
  return (
    <Toggletip align={align} className="voz-infotip">
      <ToggletipButton label={t(label)}>
        <Information />
      </ToggletipButton>
      <ToggletipContent>{children}</ToggletipContent>
    </Toggletip>
  )
}
