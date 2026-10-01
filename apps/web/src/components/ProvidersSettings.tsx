import { useCallback, useEffect, useId, useState } from 'react'
import type { FormEvent } from 'react'

import { isAbortError } from '../api/errors'
import {
  deleteProviderKey,
  listProviders,
  messageForProviderError,
  ProviderApiError,
  saveProviderKey,
  type ProviderView,
} from '../api/providers'
import './ProvidersSettings.css'

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
    <li className="provider-row">
      <div className="provider-head">
        <h3>{label}</h3>
        <span
          className={
            'provider-status' +
            (configured ? ' provider-status--configured' : '')
          }
        >
          {configured ? 'Configurado' : 'No configurado'}
        </span>
      </div>
      <form className="provider-form" onSubmit={save}>
        <label htmlFor={inputId}>{'Clave de API de ' + label}</label>
        <div className="provider-controls">
          <input
            id={inputId}
            type="password"
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
          <button type="submit" disabled={busy || key.trim() === ''}>
            Guardar
          </button>
          <button
            type="button"
            disabled={busy || !configured}
            onClick={() => {
              void run(() => deleteProviderKey(id), 'Clave eliminada.')
            }}
          >
            Eliminar
          </button>
        </div>
      </form>
      {error ? (
        <p className="provider-error" role="alert">
          {error}
        </p>
      ) : null}
      {done ? (
        <p className="provider-done" role="status">
          {done}
        </p>
      ) : null}
      <p className="provider-note">
        Tener la clave no envía nada: solo un trabajo que elijas con este
        proveedor sube audio.{' '}
        {privacyUrl !== null && /^https?:\/\//.test(privacyUrl) ? (
          <a href={privacyUrl} target="_blank" rel="noreferrer noopener">
            {'Política de privacidad de ' + label}
          </a>
        ) : null}
      </p>
    </li>
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
    <section className="providers-settings" aria-labelledby="providers-title">
      <p className="section-kicker">OPCIONAL</p>
      <h2 id="providers-title">Proveedores cloud (opcional)</h2>
      <p className="provider-intro">
        VOZ es local por defecto. Si añades una clave, podrás elegir un
        proveedor cloud para una transcripción concreta: tu audio saldrá de
        este equipo y se factura en tu cuenta del proveedor. Estas opciones son
        experimentales y nunca se recomiendan ni se eligen solas. La clave se
        guarda solo en este equipo y nunca se vuelve a mostrar.
      </p>
      {state.phase === 'loading' ? (
        <p role="status">Consultando proveedores…</p>
      ) : state.phase === 'error' ? (
        <div role="alert">
          <p>{state.message}</p>
          <button
            type="button"
            onClick={() => {
              setState({ phase: 'loading' })
              reload()
            }}
          >
            Reintentar
          </button>
        </div>
      ) : (
        <ul className="provider-list">
          {state.providers.map((provider) => (
            <ProviderRow
              key={provider.id}
              provider={provider}
              onChanged={changed}
            />
          ))}
        </ul>
      )}
    </section>
  )
}
