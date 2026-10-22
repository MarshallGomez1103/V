import { useCallback, useEffect, useId, useState } from 'react'
import type { FormEvent } from 'react'
import { Button, Checkbox, Form, PasswordInput, Stack, Tag, TextInput } from '@carbon/react'
import { Add, Connect, Edit, Save, TrashCan } from '@carbon/icons-react'

import { isAbortError } from '../api/errors'
import {
  deleteCompatibleEndpoint,
  isLoopbackUrl,
  listCompatibleEndpoints,
  messageForProviderError,
  ProviderApiError,
  saveCompatibleEndpoint,
  testCompatibleEndpoint,
  type CompatibleEndpoint,
} from '../api/providers'
import { translate, translateCode, useI18n } from '../i18n/i18n'
import { Busy } from './Busy'
import { CloudBadge } from './CloudBadge'
import { Notice } from './Notice'
import { Panel } from './Panel'

type LoadState =
  | { phase: 'loading' }
  | { phase: 'error'; message: string }
  | { phase: 'ready'; endpoints: CompatibleEndpoint[] }

type Feedback = { kind: 'success' | 'error' | 'warning'; text: string } | null

function errorText(error: unknown): string {
  return error instanceof ProviderApiError ? error.message : translate('err.provider.op')
}

function splitList(value: string): string[] {
  return [...new Set(value.split(',').map((item) => item.trim()).filter(Boolean))]
}

function hostOf(url: string): string {
  try {
    return new URL(url.trim()).host
  } catch {
    return url
  }
}

/** Scheme, host and port: what a saved key belongs to (same rule as the server). */
function originOf(url: string): string | null {
  try {
    const { protocol, hostname, port } = new URL(url.trim().replace(/\/+$/, ''))
    return `${protocol}//${hostname}:${port === '' ? (protocol === 'https:' ? '443' : '80') : port}`
  } catch {
    return null
  }
}

interface FormProps {
  endpoint: CompatibleEndpoint | null
  onDone: (saved: CompatibleEndpoint) => void
  onCancel: () => void
}

function EndpointForm({ endpoint, onDone, onCancel }: FormProps) {
  const { t } = useI18n()
  const id = useId()
  const [name, setName] = useState(endpoint?.name ?? '')
  const [baseUrl, setBaseUrl] = useState(endpoint?.base_url ?? '')
  const [key, setKey] = useState('')
  const [clearKey, setClearKey] = useState(false)
  const [stt, setStt] = useState(endpoint?.stt_models.join(', ') ?? '')
  const [tts, setTts] = useState(endpoint?.tts_models.join(', ') ?? '')
  const [voices, setVoices] = useState(endpoint?.tts_voices.join(', ') ?? '')
  // Consent is never pre-checked, not even when editing a cloud server.
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const cloud = baseUrl.trim() !== '' && !isLoopbackUrl(baseUrl)
  const insecure = cloud && /^http:/i.test(baseUrl.trim())
  const savedOrigin = endpoint ? originOf(endpoint.base_url) : null
  const newOrigin = originOf(baseUrl)
  const keyWillBeDropped =
    endpoint?.key_configured === true &&
    key.trim() === '' &&
    !clearKey &&
    savedOrigin !== null &&
    newOrigin !== null &&
    savedOrigin !== newOrigin
  const canSave =
    !busy && name.trim() !== '' && baseUrl.trim() !== '' && !insecure && (!cloud || consent)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!canSave) {
      return
    }
    setBusy(true)
    setError(null)
    void saveCompatibleEndpoint(
      {
        name: name.trim(),
        base_url: baseUrl.trim(),
        key: key.trim() === '' ? null : key.trim(),
        clear_key: clearKey,
        stt_models: splitList(stt),
        tts_models: splitList(tts),
        tts_voices: splitList(voices),
        cloud_consent: cloud && consent,
      },
      endpoint?.id,
    )
      .then((saved) => {
        setKey('')
        onDone(saved)
      })
      .catch((caught: unknown) => {
        setError(errorText(caught))
      })
      .finally(() => {
        setBusy(false)
      })
  }

  const title = endpoint ? t('ep.form.edit', { name: endpoint.name }) : t('ep.form.new')
  return (
    <Panel level={3} titleId={id + '-title'} title={title}>
      <Form onSubmit={submit}>
        <Stack gap={5}>
          <TextInput
            id={id + '-name'}
            labelText={t('ep.name')}
            value={name}
            maxLength={80}
            disabled={busy}
            onChange={(event) => {
              setName(event.target.value)
            }}
          />
          <TextInput
            id={id + '-url'}
            labelText={t('ep.url')}
            helperText={t('ep.url.help')}
            value={baseUrl}
            spellCheck={false}
            autoComplete="off"
            disabled={busy}
            onChange={(event) => {
              setBaseUrl(event.target.value)
              setConsent(false)
            }}
          />
          {insecure ? <Notice kind="error" title={t('ep.url.insecure')} /> : null}
          {cloud ? (
            <Notice
              kind="warning"
              title={t('ep.cloud.title')}
              subtitle={t('ep.cloud.body', { host: hostOf(baseUrl) })}
            />
          ) : null}
          {cloud ? (
            <Checkbox
              id={id + '-consent'}
              labelText={t('ep.cloud.consent')}
              checked={consent}
              disabled={busy}
              onChange={(_, { checked }) => {
                setConsent(checked)
              }}
            />
          ) : null}
          <PasswordInput
            id={id + '-key'}
            labelText={t('ep.key')}
            showPasswordLabel={t('prov.show')}
            hidePasswordLabel={t('prov.hide')}
            autoComplete="off"
            spellCheck={false}
            value={key}
            placeholder={endpoint?.key_configured ? t('ep.key.keep') : t('ep.key.none')}
            disabled={busy || clearKey}
            onChange={(event) => {
              setKey(event.target.value)
            }}
          />
          {keyWillBeDropped ? (
            <Notice
              kind="warning"
              title={t('ep.key.moved.title')}
              subtitle={t('ep.key.moved.body')}
            />
          ) : null}
          {endpoint?.key_configured ? (
            <Checkbox
              id={id + '-clear'}
              labelText={t('ep.key.clear')}
              checked={clearKey}
              disabled={busy}
              onChange={(_, { checked }) => {
                setClearKey(checked)
              }}
            />
          ) : null}
          <TextInput
            id={id + '-stt'}
            labelText={t('ep.stt')}
            helperText={t('ep.list.help')}
            value={stt}
            spellCheck={false}
            disabled={busy}
            onChange={(event) => {
              setStt(event.target.value)
            }}
          />
          <TextInput
            id={id + '-tts'}
            labelText={t('ep.tts')}
            helperText={t('ep.list.help')}
            value={tts}
            spellCheck={false}
            disabled={busy}
            onChange={(event) => {
              setTts(event.target.value)
            }}
          />
          <TextInput
            id={id + '-voices'}
            labelText={t('ep.voices')}
            helperText={t('ep.list.help')}
            value={voices}
            spellCheck={false}
            disabled={busy}
            onChange={(event) => {
              setVoices(event.target.value)
            }}
          />
          {error ? <Notice kind="error" title={error} /> : null}
          <div className="voz-provider__actions">
            <Button type="submit" kind="primary" size="md" renderIcon={Save} disabled={!canSave}>
              {t('common.save')}
            </Button>
            <Button kind="ghost" size="md" disabled={busy} onClick={onCancel}>
              {t('common.cancel')}
            </Button>
          </div>
        </Stack>
      </Form>
    </Panel>
  )
}

interface RowProps {
  endpoint: CompatibleEndpoint
  onEdit: () => void
  onDeleted: () => void
}

function EndpointRow({ endpoint, onEdit, onDeleted }: RowProps) {
  const { t } = useI18n()
  const id = useId()
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [feedback, setFeedback] = useState<Feedback>(null)
  const list = (items: string[]) => (items.length ? items.join(', ') : t('ep.none'))

  const test = () => {
    setBusy(true)
    setFeedback(null)
    void testCompatibleEndpoint(endpoint.id)
      .then((check) => {
        if (check.code === null) {
          setFeedback({
            kind: 'success',
            text: check.models.length
              ? t('ep.test.ok', { models: check.models.slice(0, 12).join(', ') })
              : t('ep.test.okEmpty'),
          })
          return
        }
        setFeedback({
          kind: check.reachable ? 'warning' : 'error',
          text: translateCode('ep.test.', check.code, 'ep.test.endpoint_http_error', {
            status: String(check.status ?? '?'),
          }),
        })
      })
      .catch((caught: unknown) => {
        setFeedback({ kind: 'error', text: errorText(caught) })
      })
      .finally(() => {
        setBusy(false)
      })
  }

  const remove = () => {
    if (!confirming) {
      setConfirming(true)
      return
    }
    setBusy(true)
    void deleteCompatibleEndpoint(endpoint.id)
      .then(onDeleted)
      .catch((caught: unknown) => {
        setFeedback({ kind: 'error', text: errorText(caught) })
        setBusy(false)
        setConfirming(false)
      })
  }

  return (
    <Panel
      level={3}
      titleId={id + '-title'}
      title={endpoint.name}
      actions={
        endpoint.cloud ? (
          <CloudBadge />
        ) : (
          <Tag type="green" size="sm">
            {t('ep.local')}
          </Tag>
        )
      }
    >
      <dl className="voz-endpoint__facts">
        <dt>{t('ep.url')}</dt>
        <dd>
          <code>{endpoint.base_url}</code>
        </dd>
        <dt>{t('ep.stt')}</dt>
        <dd>{list(endpoint.stt_models)}</dd>
        <dt>{t('ep.tts')}</dt>
        <dd>{list(endpoint.tts_models)}</dd>
        {endpoint.tts_models.length ? (
          <>
            <dt>{t('ep.voices')}</dt>
            <dd>{list(endpoint.tts_voices)}</dd>
          </>
        ) : null}
        {endpoint.key_configured ? (
          <>
            <dt>{t('ep.key')}</dt>
            <dd>{t('ep.key.saved')}</dd>
          </>
        ) : null}
      </dl>
      <div className="voz-provider__actions">
        <Button kind="tertiary" size="md" renderIcon={Connect} disabled={busy} onClick={test}>
          {t('ep.test')}
        </Button>
        <Button kind="ghost" size="md" renderIcon={Edit} disabled={busy} onClick={onEdit}>
          {t('ep.edit')}
        </Button>
        <Button
          kind={confirming ? 'danger' : 'danger--tertiary'}
          size="md"
          renderIcon={TrashCan}
          disabled={busy}
          onClick={remove}
        >
          {confirming ? t('ep.delete.confirm') : t('common.delete')}
        </Button>
      </div>
      {feedback ? <Notice kind={feedback.kind} title={feedback.text} /> : null}
    </Panel>
  )
}

/** Sección «Servidores compatibles con OpenAI» de la pantalla de proveedores. */
export function CompatibleEndpoints({ onChanged }: { onChanged?: (() => void) | undefined }) {
  const { t } = useI18n()
  const [state, setState] = useState<LoadState>({ phase: 'loading' })
  const [attempt, setAttempt] = useState(0)
  // `null`: no form; `'new'`: adding; otherwise the id being edited.
  const [editing, setEditing] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void listCompatibleEndpoints(controller.signal)
      .then((endpoints) => {
        setState({ phase: 'ready', endpoints })
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

  const changed = useCallback(
    (message: string) => {
      setEditing(null)
      setDone(message)
      setAttempt((current) => current + 1)
      onChanged?.()
    },
    [onChanged],
  )

  const endpoints = state.phase === 'ready' ? state.endpoints : []
  const editedEndpoint = endpoints.find((item) => item.id === editing) ?? null

  return (
    <section className="voz-endpoints" aria-labelledby="endpoints-title">
      <h2 id="endpoints-title" className="voz-section-title">
        {t('ep.title')}
      </h2>
      <p className="voz-field-note">{t('ep.desc')}</p>
      {done ? <Notice kind="success" title={done} /> : null}
      {state.phase === 'loading' ? (
        <div role="status">
          <Busy description={t('ep.loading')} />
        </div>
      ) : state.phase === 'error' ? (
        <Notice
          kind="error"
          title={state.message}
          action={{
            label: t('common.retry'),
            onClick: () => {
              setState({ phase: 'loading' })
              setAttempt((current) => current + 1)
            },
          }}
        />
      ) : (
        <>
          {endpoints.length === 0 && editing === null ? (
            <p className="voz-field-note">{t('ep.empty')}</p>
          ) : null}
          {endpoints.map((endpoint) =>
            endpoint.id === editing ? (
              <EndpointForm
                key={endpoint.id}
                endpoint={endpoint}
                onDone={() => {
                  changed(t('ep.saved'))
                }}
                onCancel={() => {
                  setEditing(null)
                }}
              />
            ) : (
              <EndpointRow
                key={endpoint.id}
                endpoint={endpoint}
                onEdit={() => {
                  setDone(null)
                  setEditing(endpoint.id)
                }}
                onDeleted={() => {
                  changed(t('ep.deleted'))
                }}
              />
            ),
          )}
          {editing === 'new' ? (
            <EndpointForm
              endpoint={null}
              onDone={() => {
                changed(t('ep.saved'))
              }}
              onCancel={() => {
                setEditing(null)
              }}
            />
          ) : editing === null || editedEndpoint === null ? (
            <div>
              <Button
                kind="tertiary"
                size="md"
                renderIcon={Add}
                onClick={() => {
                  setDone(null)
                  setEditing('new')
                }}
              >
                {t('ep.add')}
              </Button>
            </div>
          ) : null}
        </>
      )}
    </section>
  )
}
