import './CloudBadge.css'

/** Insignia "CLOUD": marca todo lo que envía audio fuera del equipo (S11.09). */
export function CloudBadge() {
  return (
    <span className="cloud-badge" title="El audio sale de tu equipo">
      CLOUD
    </span>
  )
}
