import { Tag } from '@carbon/react'

import { Term } from './Hint'

/** Insignia «CLOUD»: marca todo lo que envía audio fuera del equipo (S11.09). */
export function CloudBadge({ plain = false }: { plain?: boolean }) {
  return (
    <Tag type="magenta" size="sm">
      <Term definition="term.cloud.def" plain={plain}>
        CLOUD
      </Term>
    </Tag>
  )
}
