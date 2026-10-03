import { Tag } from '@carbon/react'

/** Insignia "CLOUD": marca todo lo que envía audio fuera del equipo (S11.09). */
export function CloudBadge() {
  return (
    <Tag type="magenta" size="sm" title="El audio sale de tu equipo">
      CLOUD
    </Tag>
  )
}
