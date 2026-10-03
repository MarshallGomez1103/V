import { useEffect, useId, useState } from 'react'
import { Button, TextArea } from '@carbon/react'

import { getGlossary, putGlossary, type Glossary } from '../api/glossary'
import { useI18n } from '../i18n/i18n'
import { Busy } from './Busy'
import { Notice } from './Notice'
import './GlossaryEditor.scss'

export interface GlossaryEditorProps {
  projectId: string
  disabled?: boolean
}

/** `key` es el proyecto consultado: si no coincide con el actual, sigue cargando. */
type LoadResult =
  | { key: string; phase: 'error'; message: string | null }
  | { key: string; phase: 'ready'; glossary: Glossary }

/** Mismo criterio que el backend: recorta, descarta vacíos y duplicados. */
function parseTerms(text: string): string[] {
  const seen = new Set<string>()
  for (const line of text.split('\n')) {
    const term = line.trim()
    if (term) {
      seen.add(term)
    }
  }
  return [...seen]
}

function messageOf(error: unknown): string | null {
  return error instanceof Error ? error.message : null
}

export function GlossaryEditor({ projectId, disabled = false }: GlossaryEditorProps) {
  const { t, tn } = useI18n()
  const fieldId = useId()
  const [result, setResult] = useState<LoadResult | null>(null)
  const [text, setText] = useState('')
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null | undefined>(undefined)

  useEffect(() => {
    const controller = new AbortController()
    getGlossary(projectId, controller.signal)
      .then((glossary) => {
        setText(glossary.terms.join('\n'))
        setResult({ key: projectId, phase: 'ready', glossary })
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setResult({ key: projectId, phase: 'error', message: messageOf(error) })
        }
      })
    return () => {
      controller.abort()
    }
  }, [projectId])

  const state = result?.key === projectId ? result : null

  if (state === null) {
    return (
      <div aria-live="polite">
        <Busy description={t('gloss.loading')} />
      </div>
    )
  }
  if (state.phase === 'error') {
    return <Notice kind="error" title={state.message ?? t('err.glossary.generic')} />
  }

  const { glossary } = state
  const terms = parseTerms(text)
  const tooMany = terms.length > glossary.max_terms
  const tooLong = terms.some((term) => term.length > glossary.max_term_length)
  const invalid = tooMany || tooLong

  async function save() {
    setSaving(true)
    setStatus(null)
    setSaveError(undefined)
    try {
      const saved = await putGlossary(projectId, terms)
      setText(saved.terms.join('\n'))
      setResult({ key: projectId, phase: 'ready', glossary: saved })
      setStatus(tn('gloss.saved', saved.terms.length))
    } catch (error: unknown) {
      setSaveError(messageOf(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="voz-glossary" aria-label={t('gloss.region')}>
      <TextArea
        id={fieldId}
        labelText={t('gloss.label')}
        rows={5}
        value={text}
        disabled={disabled || saving}
        placeholder={t('gloss.placeholder')}
        helperText={t('gloss.helper', {
          count: terms.length,
          max: glossary.max_terms,
          length: glossary.max_term_length,
        })}
        invalid={invalid}
        invalidText={
          tooMany
            ? t('gloss.tooMany', { max: glossary.max_terms })
            : t('gloss.tooLong', { length: glossary.max_term_length })
        }
        onChange={(event) => {
          setText(event.target.value)
          setStatus(null)
        }}
      />
      <p className="voz-field-note">
        {glossary.applies_to.length > 0
          ? t('gloss.appliesTo', { engines: glossary.applies_to.join(', ') })
          : t('gloss.appliesNone')}
      </p>
      {saveError !== undefined ? (
        <Notice kind="error" title={saveError ?? t('err.glossary.generic')} />
      ) : null}
      {status ? <Notice kind="success" title={status} /> : null}
      <div>
        <Button
          kind="tertiary"
          size="md"
          disabled={disabled || saving || invalid}
          onClick={() => void save()}
        >
          {saving ? t('gloss.saving') : t('gloss.save')}
        </Button>
      </div>
    </section>
  )
}
