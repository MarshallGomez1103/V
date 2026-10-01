import { useEffect, useId, useState } from 'react'

import { getGlossary, putGlossary, type Glossary } from '../api/glossary'
import './GlossaryEditor.css'

export interface GlossaryEditorProps {
  projectId: string
  disabled?: boolean
}

/** `key` es el proyecto consultado: si no coincide con el actual, sigue cargando. */
type LoadResult =
  | { key: string; phase: 'error'; message: string }
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

function messageOf(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'No se pudo completar la operación con el glosario.'
}

export function GlossaryEditor({ projectId, disabled = false }: GlossaryEditorProps) {
  const fieldId = useId()
  const [result, setResult] = useState<LoadResult | null>(null)
  const [text, setText] = useState('')
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

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
    return <p className="glossary-editor-note">Cargando glosario…</p>
  }
  if (state.phase === 'error') {
    return (
      <p className="glossary-editor-note" role="alert">
        {state.message}
      </p>
    )
  }

  const { glossary } = state
  const terms = parseTerms(text)
  const tooMany = terms.length > glossary.max_terms
  const tooLong = terms.some((term) => term.length > glossary.max_term_length)
  const invalid = tooMany || tooLong

  async function save() {
    setSaving(true)
    setStatus(null)
    setSaveError(null)
    try {
      const saved = await putGlossary(projectId, terms)
      setText(saved.terms.join('\n'))
      setResult({ key: projectId, phase: 'ready', glossary: saved })
      setStatus('Glosario guardado (' + String(saved.terms.length) + ' términos).')
    } catch (error: unknown) {
      setSaveError(messageOf(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="glossary-editor" aria-label="Editor de glosario">
      <label htmlFor={fieldId} className="glossary-editor-label">
        Glosario del proyecto
      </label>
      <textarea
        id={fieldId}
        className="glossary-editor-input"
        rows={5}
        value={text}
        disabled={disabled || saving}
        placeholder="Un término por línea (nombres propios, siglas, vocabulario técnico)"
        onChange={(event) => {
          setText(event.target.value)
          setStatus(null)
        }}
      />
      <p className="glossary-editor-note">
        {String(terms.length)} de {String(glossary.max_terms)} términos, hasta{' '}
        {String(glossary.max_term_length)} caracteres cada uno. Ayuda al motor a
        acertar esas palabras; no cambia el texto transcrito.
      </p>
      <p className="glossary-editor-note">
        {glossary.applies_to.length > 0
          ? 'Lo usan: ' + glossary.applies_to.join(', ') + '. Los demás motores lo ignoran.'
          : 'Ningún motor instalado usa el glosario.'}
      </p>
      {invalid ? (
        <p className="glossary-editor-error" role="alert">
          {tooMany
            ? 'Hay demasiados términos (máximo ' + String(glossary.max_terms) + ').'
            : 'Algún término supera los ' +
              String(glossary.max_term_length) +
              ' caracteres.'}
        </p>
      ) : null}
      {saveError ? (
        <p className="glossary-editor-error" role="alert">
          {saveError}
        </p>
      ) : null}
      {status ? <p role="status">{status}</p> : null}
      <button
        type="button"
        className="glossary-editor-save"
        disabled={disabled || saving || invalid}
        onClick={() => void save()}
      >
        {saving ? 'Guardando…' : 'Guardar glosario'}
      </button>
    </section>
  )
}
