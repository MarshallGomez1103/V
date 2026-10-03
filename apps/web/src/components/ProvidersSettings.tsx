import { useCallback, useEffect, useId, useState } from 'react'
import type { FormEvent } from 'react'
import { Button, Column, Form, Grid, Link, PasswordInput, Stack, Tag } from '@carbon/react'
import { Save, TrashCan } from '@carbon/icons-react'

import { isAbortError } from '../api/errors'
import {
  deleteProviderKey,
  listProviders,
  messageForProviderError,
  ProviderApiError,
  saveProviderKey,
  type ProviderView,
} from '../api/providers'
import { Busy } from './Busy'
import { Notice } from './Notice'
import { Panel } from './Panel'
import './ProvidersSettings.scss'

type LoadState =
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; providers: ProviderView[] }

function errorMessage(error: unknown): string {
  return error instanceof ProviderApiError
    ? error.message
    : 'No se pudo completar la operación. Inténtalo de nuevo.'
}

interface ProviderRowProps {
  provider: ProviderView
  onChanged: () => void
}

function ProviderRow({ provider, onChanged }: ProviderRowProps) {
  const { id, label, configured, privacy_url: privacyUrl } = provider
  const inputId = useId()
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)

  const run = async (action: () => Promise<void>, success: string) => {
    setBusy(true)
    setError(null)
    setDone(null)
    try {
      await action()
      setKey('')
      setDone(success)
      onChanged()
    } catch (caught: unknown) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  const save = (event: FormEvent) => {
    event.preventDefault()
    if (key.trim() === '') {
      return
    }
    void run(() => saveProviderKey(id, key.trim()), 'Clave guardada.')
  }

  return (
    <Panel
      level={3}
      titleId={inputId + '-title'}
      title={label}
      actions={
        <Tag type={configured ? 'green' : 'gray'} size="md">
          {configured ? 'Configurado' : 'No configurado'}
        </Tag>
      }
    >
      <Form onSubmit={save}>
        <Stack gap={5}>
          <PasswordInput
            id={inputId}
            labelText={'Clave de API de ' + label}
            showPasswordLabel="Mostrar la clave"
            hidePasswordLabel="Ocultar la clave"
            autoComplete="off"
            spellCheck={false}
            value={key}
            placeholder={
              configured
                ? 'Pega una clave nueva para reemplazarla'
                : 'Pega tu clave'
            }
            disabled={busy}
            onChange={(event) => {
              setKey(event.target.value)
            }}
          />
          <div className="voz-provider__actions">
            <Button
              type="submit"
              kind="primary"
              size="md"
              renderIcon={Save}
              disabled={busy || key.trim() === ''}
            >
              Guardar
            </Button>
            <Button
              kind="danger--tertiary"
              size="md"
              renderIcon={TrashCan}
              disabled={busy || !configured}
              onClick={() => {
                void run(() => deleteProviderKey(id), 'Clave eliminada.')
              }}
            >
              Eliminar
            </Button>
          </div>
        </Stack>
      </Form>
      {error ? <Notice kind="error" title={error} /> : null}
      {done ? <Notice kind="success" title={done} /> : null}
      <p className="voz-field-note">
        Tener la clave no envía nada: solo un trabajo que elijas con este
        proveedor sube audio.{' '}
        {privacyUrl !== null && /^https?:\/\//.test(privacyUrl) ? (
          <Link href={privacyUrl} target="_blank" rel="noreferrer noopener">
            {'Política de privacidad de ' + label}
          </Link>
        ) : null}
      </p>
    </Panel>
  )
}

export function ProvidersSettings({
  onChanged,
}: { onChanged?: () => void } = {}) {
  const [state, setState] = useState<LoadState>({ phase: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    void listProviders(controller.signal)
      .then((providers) => {
        setState({ phase: 'ready', providers })
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          setState({
            phase: 'error',
            message:
              error instanceof ProviderApiError
                ? error.message
                : messageForProviderError('unknown'),
          })
        }
      })
    return () => {
      controller.abort()
    }
  }, [attempt])

  const reload = useCallback(() => {
    setAttempt((current) => current + 1)
  }, [])
  const changed = useCallback(() => {
    reload()
    onChanged?.()
  }, [onChanged, reload])

  return (
    <section className="voz-providers" aria-labelledby="providers-title">
      <h2 id="providers-title" className="voz-section-title">
        Claves de API
      </h2>
      <Notice
        kind="info"
        title="VOZ es local por defecto."
        subtitle="Si añades una clave, podrás elegir un proveedor cloud para una transcripción concreta: tu audio saldrá de este equipo y se factura en tu cuenta del proveedor. Estas opciones son experimentales y nunca se recomiendan ni se eligen solas. La clave se guarda solo en este equipo y nunca se vuelve a mostrar."
      />
      {state.phase === 'loading' ? (
        <div role="status">
          <Busy description="Consultando proveedores…" />
        </div>
      ) : state.phase === 'error' ? (
        <Notice
          kind="error"
          title={state.message}
          action={{
            label: 'Reintentar',
            onClick: () => {
              setState({ phase: 'loading' })
              reload()
            },
          }}
        />
      ) : (
        <Grid narrow className="voz-providers__grid">
          {state.providers.map((provider) => (
            <Column key={provider.id} sm={4} md={8} lg={8}>
              <ProviderRow provider={provider} onChanged={changed} />
            </Column>
          ))}
        </Grid>
      )}
    </section>
  )
}
