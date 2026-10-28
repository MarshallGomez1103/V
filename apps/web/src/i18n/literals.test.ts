/// <reference types="vite/client" />
import ts from 'typescript'
import { describe, expect, it } from 'vitest'

import { MESSAGES } from './messages'

const VISIBLE_ATTRIBUTES = new Set([
  'aria-label',
  'aria-description',
  'title',
  'placeholder',
  'alt',
  'labelText',
  'label',
  'text',
  'description',
  'subtitle',
  'heading',
  'modalHeading',
  'modalLabel',
  'primaryButtonText',
  'secondaryButtonText',
  'closeButtonLabel',
  'iconDescription',
  'statusIconDescription',
  'helperText',
  'invalidText',
  'legendText',
])

// Siglas y nombres propios que se escriben igual en todos los idiomas.
const PROPER_NAMES = new Set([
  'CLOUD',
  'VAD',
  'Faster Whisper',
  'whisper.cpp',
  'sherpa-onnx TTS',
  'sherpa-onnx ASR',
])

const LETTERS = /[A-Za-zÁÉÍÓÚáéíóúñÑ]{2,}/

/** Textos visibles escritos a mano en JSX (no claves del catálogo ni nombres propios). */
function findVisibleLiterals(source: string): string[] {
  const file = ts.createSourceFile('x.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const found: string[] = []
  const check = (text: string) => {
    const value = text.trim()
    if (LETTERS.test(value) && !PROPER_NAMES.has(value) && !Object.hasOwn(MESSAGES, value)) {
      found.push(value)
    }
  }
  const visit = (node: ts.Node) => {
    if (ts.isJsxText(node)) {
      check(node.getText())
    } else if (ts.isJsxAttribute(node) && VISIBLE_ATTRIBUTES.has(node.name.getText()) && node.initializer) {
      const init = node.initializer
      if (ts.isStringLiteral(init)) {
        check(init.text)
      } else if (
        ts.isJsxExpression(init) &&
        init.expression !== undefined &&
        (ts.isStringLiteral(init.expression) || ts.isNoSubstitutionTemplateLiteral(init.expression))
      ) {
        check(init.expression.text)
      }
    } else if (
      ts.isJsxExpression(node) &&
      node.expression !== undefined &&
      ts.isStringLiteral(node.expression) &&
      (ts.isJsxElement(node.parent) || ts.isJsxFragment(node.parent))
    ) {
      check(node.expression.text)
    }
    ts.forEachChild(node, visit)
  }
  visit(file)
  return found
}

describe('textos visibles fuera del catálogo', () => {
  it('detecta texto suelto, atributos visibles y expresiones literales', () => {
    const sample = `
      export const A = () => (
        <div title="Cerrar" aria-label={'Abrir menú'}>
          Hola
          <span>{'Adiós'}</span>
          <button aria-label={t('common.close')} className="btn primary">{t('common.retry')}</button>
        </div>
      )`
    expect(findVisibleLiterals(sample)).toEqual(['Cerrar', 'Abrir menú', 'Hola', 'Adiós'])
  })

  it('ningún componente escribe texto visible a mano', () => {
    const sources = import.meta.glob<string>(['../**/*.tsx', '!../**/*.test.tsx'], {
      query: '?raw',
      import: 'default',
      eager: true,
    })
    const files = Object.entries(sources)
    expect(files.length).toBeGreaterThan(30)
    const offenders = files.flatMap(([path, source]) =>
      findVisibleLiterals(source).map((text) => path + ': ' + text),
    )
    expect(offenders).toEqual([])
  })
})
