import type { ReactNode } from 'react'
import { Layer } from '@carbon/react'

import './Panel.scss'

export interface PanelProps {
  /** Id del encabezado; el panel queda etiquetado por él. */
  titleId: string
  title: string
  description?: ReactNode
  /** Controles a la derecha del título (botones, menús, estado). */
  actions?: ReactNode
  /** Nivel del encabezado (2 por defecto). */
  level?: 2 | 3
  className?: string
  children: ReactNode
}

/**
 * Superficie base de la app: un panel con fondo de capa Carbon, título y
 * acciones. Los campos que contiene reciben el nivel de capa correcto
 * (`Layer`), así que usan los tokens `field-02` sobre el fondo del panel.
 */
export function Panel({
  titleId,
  title,
  description,
  actions,
  level = 2,
  className,
  children,
}: PanelProps) {
  const Heading = level === 2 ? 'h2' : 'h3'
  return (
    <Layer withBackground>
      <section
        className={'voz-panel' + (className ? ' ' + className : '')}
        aria-labelledby={titleId}
      >
        <header className="voz-panel__header">
          <div className="voz-panel__heading">
            <Heading id={titleId} className="voz-panel__title">
              {title}
            </Heading>
            {description ? (
              <p className="voz-panel__description">{description}</p>
            ) : null}
          </div>
          {actions ? <div className="voz-panel__actions">{actions}</div> : null}
        </header>
        <div className="voz-panel__body">{children}</div>
      </section>
    </Layer>
  )
}
