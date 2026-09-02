import { HealthStatus } from './components/HealthStatus'

const waveformHeights = [28, 52, 36, 68, 42, 78, 54, 32, 64, 86, 48, 70, 38, 58, 30]

function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <span />
      <span />
      <span />
      <span />
      <span />
    </span>
  )
}

function LockIcon() {
  return (
    <svg
      aria-hidden="true"
      className="lock-icon"
      viewBox="0 0 24 24"
      fill="none"
    >
      <path d="M7.5 10V7.5a4.5 4.5 0 0 1 9 0V10" />
      <rect x="5" y="10" width="14" height="11" rx="3" />
      <path d="M12 14.5v2" />
    </svg>
  )
}

export function App() {
  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#main" aria-label="VOZ, ir al inicio">
          <BrandMark />
          <span>VOZ</span>
        </a>
        <div className="privacy-badge">
          <LockIcon />
          <span>Local y privado</span>
        </div>
      </header>

      <main id="main">
        <section className="hero" aria-labelledby="hero-title">
          <div className="eyebrow">
            <span className="eyebrow-dot" aria-hidden="true" />
            Tu audio. Tus palabras. Tu equipo.
          </div>
          <h1 id="hero-title">
            Escucha menos.
            <br />
            <span>Encuentra más.</span>
          </h1>
          <p className="hero-copy">
            VOZ será tu espacio local para convertir clases, entrevistas y
            grabaciones largas en texto editable, sin entregar tus archivos a
            terceros.
          </p>
        </section>

        <section className="workspace-grid" aria-label="Inicio de VOZ">
          <article className="import-card" aria-labelledby="import-title">
            <div className="card-heading">
              <div>
                <p className="section-kicker">NUEVO PROYECTO</p>
                <h2 id="import-title">Trae una grabación</h2>
              </div>
              <span className="coming-soon">Próximamente</span>
            </div>

            <div
              className="drop-zone"
              aria-disabled="true"
              aria-describedby="import-description"
            >
              <div className="wave-preview" aria-hidden="true">
                {waveformHeights.map((height, index) => (
                  <span
                    key={height + '-' + index}
                    style={{ height: height + '%' }}
                  />
                ))}
              </div>
              <h3>La importación está en construcción</h3>
              <p id="import-description">
                Aquí podrás soltar audio o video compatible con FFmpeg. Todavía
                no se cargará ni procesará ningún archivo.
              </p>
              <button type="button" disabled>
                Importar archivo
              </button>
              <small>El archivo original siempre se conservará intacto.</small>
            </div>
          </article>

          <aside className="status-column" aria-label="Estado de la aplicación">
            <HealthStatus />

            <article className="promise-card">
              <p className="section-kicker">PRIVACIDAD POR DISEÑO</p>
              <h2>Lo tuyo se queda contigo.</h2>
              <p>
                VOZ priorizará motores locales y funcionará sin Internet una
                vez estén instalados los modelos elegidos.
              </p>
              <ul>
                <li>
                  <span aria-hidden="true">01</span>
                  Original inmutable
                </li>
                <li>
                  <span aria-hidden="true">02</span>
                  Procesamiento recuperable
                </li>
                <li>
                  <span aria-hidden="true">03</span>
                  Proveedores intercambiables
                </li>
              </ul>
            </article>
          </aside>
        </section>

        <section className="recent" aria-labelledby="recent-title">
          <div>
            <p className="section-kicker">BIBLIOTECA</p>
            <h2 id="recent-title">Proyectos recientes</h2>
          </div>
          <p className="empty-state">
            Aún no hay proyectos. Tu biblioteca local aparecerá aquí.
          </p>
        </section>
      </main>

      <footer>
        <span>VOZ 0.1.0</span>
        <span>Hecho para trabajar en local</span>
      </footer>
    </div>
  )
}
