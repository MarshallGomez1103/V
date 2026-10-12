import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { Column, Content, Grid, Theme } from '@carbon/react'

import type { JobView } from './api/jobs'
import type { LibraryItem } from './api/library'
import { Busy } from './components/Busy'
import { AppHeader } from './components/AppHeader'
import { ClosedScreen } from './components/ClosedScreen'
import { HealthStatus } from './components/HealthStatus'
import { Library } from './components/Library'
import { NewTranscription } from './components/NewTranscription'
import type { ImportResult } from './components/NewProjectCard'
import { ServerBanner } from './components/ServerBanner'
import { useLibrary } from './hooks/useLibrary'
import { useRoute } from './hooks/useRoute'
import { useServerStatus } from './hooks/useServerStatus'
import { useI18n } from './i18n/i18n'
import type { MessageKey } from './i18n/messages'
import { HOME, type Route } from './lib/navigation'
import { useAppearance } from './theme/appearance'
import './App.scss'

// Vistas secundarias: chunks aparte para mantener pequeño el bundle inicial.
const Workspace = lazy(() =>
  import('./components/Workspace').then((m) => ({ default: m.Workspace })),
)
const SpeakWorkspace = lazy(() =>
  import('./components/SpeakWorkspace').then((m) => ({ default: m.SpeakWorkspace })),
)
const ModelManager = lazy(() =>
  import('./components/ModelManager').then((m) => ({ default: m.ModelManager })),
)
const ProvidersSettings = lazy(() =>
  import('./components/ProvidersSettings').then((m) => ({ default: m.ProvidersSettings })),
)

type PageName = 'home' | 'nueva' | 'speak' | 'modelos' | 'proveedores'

const PAGE_KEYS: Record<PageName, { title: MessageKey; description: MessageKey }> = {
  home: { title: 'page.inicio.title', description: 'page.inicio.description' },
  nueva: { title: 'page.transcribir.title', description: 'page.transcribir.description' },
  speak: { title: 'page.speak.title', description: 'page.speak.description' },
  modelos: { title: 'page.modelos.title', description: 'page.modelos.description' },
  proveedores: {
    title: 'page.proveedores.title',
    description: 'page.proveedores.description',
  },
}

function PageHeader({ page }: { page: PageName }) {
  const { t } = useI18n()
  const keys = PAGE_KEYS[page]
  return (
    <header className="voz-page__header">
      <h1 className="voz-page__title">{t(keys.title)}</h1>
      <p className="voz-page__description">{t(keys.description)}</p>
    </header>
  )
}

export function App() {
  const { t } = useI18n()
  const { resolved, accent } = useAppearance()
  const [closed, setClosed] = useState(false)
  const server = useServerStatus(!closed)
  const library = useLibrary()
  const [route, navigate] = useRoute()
  // Grabación del último trabajo creado en esta sesión: el espacio de trabajo la usa de inmediato.
  const [seed, setSeed] = useState<ImportResult | null>(null)
  // `key` reinicia la pantalla «Nueva» (tras crear un trabajo o al ajustar uno ya hecho).
  const [fresh, setFresh] = useState<{ key: number; initial: ImportResult | null }>({
    key: 0,
    initial: null,
  })
  // Voz/Modelos/Proveedores se montan en la primera visita y luego se conservan ocultos
  // (el texto escrito en Voz sobrevive a un paso por Modelos).
  const [visited, setVisited] = useState({ speak: false, modelos: false, proveedores: false })
  if (
    (route.name === 'speak' && !visited.speak) ||
    (route.name === 'modelos' && !visited.modelos) ||
    (route.name === 'proveedores' && !visited.proveedores)
  ) {
    setVisited({
      speak: visited.speak || route.name === 'speak',
      modelos: visited.modelos || route.name === 'modelos',
      proveedores: visited.proveedores || route.name === 'proveedores',
    })
  }
  const [modelsVersion, setModelsVersion] = useState(0)
  const refreshModels = useCallback(() => {
    setModelsVersion((version) => version + 1)
  }, [])

  // Al volver a Inicio la lista se actualiza (jobs nuevos, estados, borrados).
  const { reload: reloadLibrary } = library
  const homeActive = route.name === 'home'
  useEffect(() => {
    if (homeActive) {
      reloadLibrary()
    }
  }, [homeActive, reloadLibrary])

  useEffect(() => {
    document.title = closed ? t('closed.doc') : t('app.title')
  }, [closed, t])

  const openItem = useCallback(
    (item: LibraryItem) => {
      if (item.latest_job !== null) {
        navigate({ name: 'trabajo', jobId: item.latest_job.id })
      }
    },
    [navigate],
  )
  const created = useCallback(
    (job: JobView, imported: ImportResult) => {
      setSeed(imported)
      setFresh((current) => ({ key: current.key + 1, initial: null }))
      navigate({ name: 'trabajo', jobId: job.id })
    },
    [navigate],
  )
  const adjust = useCallback(
    (imported: ImportResult) => {
      setFresh((current) => ({ key: current.key + 1, initial: imported }))
      navigate({ name: 'nueva' })
    },
    [navigate],
  )
  const goTo = useCallback(
    (target: Route) => {
      navigate(target)
    },
    [navigate],
  )

  if (closed) {
    return <ClosedScreen />
  }

  const processing =
    library.phase === 'ready' &&
    library.items.some(
      (item) =>
        item.latest_job !== null &&
        !['COMPLETED', 'FAILED', 'CANCELLED'].includes(item.latest_job.state),
    )

  return (
    <Theme theme={resolved} className="voz-app" {...{ 'data-accent': accent }}>
      <AppHeader
        route={route}
        onNavigate={goTo}
        jobActive={processing}
        onClosed={() => {
          setClosed(true)
        }}
      />

      <Content id="main-content" className="voz-content">
        {server.down ? (
          <div className="voz-banner">
            <ServerBanner onRetry={server.check} />
          </div>
        ) : null}

        {route.name === 'home' ? (
          <Grid narrow className="voz-grid">
            <Column sm={4} md={8} lg={16}>
              <PageHeader page="home" />
              {server.down ? null : <HealthStatus />}
            </Column>
            <Column sm={4} md={8} lg={16}>
              <Library
                state={library}
                onReload={library.reload}
                onOpen={openItem}
                onNew={() => {
                  goTo({ name: 'nueva' })
                }}
              />
            </Column>
          </Grid>
        ) : null}

        <div hidden={route.name !== 'nueva'}>
          <NewTranscription
            key={fresh.key}
            initialImported={fresh.initial}
            modelsVersion={modelsVersion}
            onCreated={created}
            header={
              <>
                <PageHeader page="nueva" />
                {server.down || route.name !== 'nueva' ? null : <HealthStatus />}
              </>
            }
          />
        </div>

        {route.name === 'trabajo' ? (
          <Suspense fallback={<Busy description={t('common.loading')} />}>
            <Workspace
              key={route.jobId}
              jobId={route.jobId}
              seed={seed}
              library={library}
              onAdjust={adjust}
              onGoHome={() => {
                goTo(HOME)
              }}
              onOpenModels={() => {
                goTo({ name: 'modelos' })
              }}
            />
          </Suspense>
        ) : null}

        <div hidden={route.name !== 'speak'}>
          <Grid narrow className="voz-grid">
            <Column sm={4} md={8} lg={16}>
              <PageHeader page="speak" />
              {visited.speak ? (
                <Suspense fallback={<Busy description={t('common.loading')} />}>
                  <SpeakWorkspace
                    modelsVersion={modelsVersion}
                    onOpenModels={() => {
                      goTo({ name: 'modelos' })
                    }}
                  />
                </Suspense>
              ) : null}
            </Column>
          </Grid>
        </div>

        <div hidden={route.name !== 'modelos'}>
          <Grid narrow className="voz-grid">
            <Column sm={4} md={8} lg={16}>
              <PageHeader page="modelos" />
              {visited.modelos ? (
                <Suspense fallback={<Busy description={t('common.loading')} />}>
                  <ModelManager onModelsChanged={refreshModels} />
                </Suspense>
              ) : null}
            </Column>
          </Grid>
        </div>

        <div hidden={route.name !== 'proveedores'}>
          <Grid narrow className="voz-grid">
            <Column sm={4} md={8} lg={16}>
              <PageHeader page="proveedores" />
              {visited.proveedores ? (
                <Suspense fallback={<Busy description={t('common.loading')} />}>
                  <ProvidersSettings onChanged={refreshModels} />
                </Suspense>
              ) : null}
            </Column>
          </Grid>
        </div>
      </Content>
    </Theme>
  )
}
