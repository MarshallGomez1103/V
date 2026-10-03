import { useEffect, useState, useSyncExternalStore } from 'react'

import { translate } from '../i18n/i18n'
import {
  SegmentConflictError,
  updateSegment,
  type EditableSegment,
} from '../api/segments'

export const AUTOSAVE_DEBOUNCE_MS = 800

export type SegmentDraftStatus =
  | 'idle'
  | 'dirty'
  | 'saving'
  | 'saved'
  | 'error'
  | 'conflict'

/** Borrador de un segmento. Inmutable: cada cambio crea un objeto nuevo. */
export interface SegmentDraft {
  /** Última versión conocida en el servidor (base de la próxima revisión). */
  base: EditableSegment
  /** Texto del usuario. */
  text: string
  status: Exclude<SegmentDraftStatus, 'idle'>
  /** Versión del servidor cuando hubo conflicto. */
  conflict?: EditableSegment
  errorMessage?: string
}

export type AggregateStatus = 'saved' | 'dirty' | 'saving' | 'error' | 'conflict'

// Prioridad: lo que exige acción del usuario gana a lo que sigue en curso.
const PRIORITY: AggregateStatus[] = [
  'conflict',
  'error',
  'saving',
  'dirty',
  'saved',
]

/**
 * Almacén de borradores por id de segmento. Vive fuera de las filas para que
 * desmontarlas no pierda texto. Guardados serializados: un solo PUT en vuelo
 * por segmento; si hay más cambios, al terminar se envía solo el último.
 */
export class SegmentDraftStore {
  private drafts = new Map<string, SegmentDraft>()
  private timers = new Map<string, ReturnType<typeof setTimeout>>()
  private inflight = new Set<string>()
  private listeners = new Set<() => void>()
  private aggregate: AggregateStatus = 'saved'

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }

  getDraft = (id: string): SegmentDraft | undefined => this.drafts.get(id)

  getStatus = (): AggregateStatus => this.aggregate

  /** Hay cambios del usuario que el servidor todavía no confirmó. */
  hasPending = (): boolean => this.aggregate !== 'saved'

  /** Registra texto nuevo; guarda solo tras `AUTOSAVE_DEBOUNCE_MS` sin teclear. */
  edit = (segment: EditableSegment, text: string): void => {
    const current = this.drafts.get(segment.id)
    const base = current?.base ?? {
      id: segment.id,
      text: segment.text,
      revision: segment.revision,
    }
    // En conflicto el usuario sigue editando su versión sin autosave.
    const status = current?.status === 'conflict' ? 'conflict' : 'dirty'
    this.put(segment.id, { ...current, base, text, status })
    if (status === 'dirty') {
      this.clearTimer(segment.id)
      this.timers.set(
        segment.id,
        setTimeout(() => {
          this.timers.delete(segment.id)
          void this.run(segment.id)
        }, AUTOSAVE_DEBOUNCE_MS),
      )
    }
  }

  /** Guarda ya (al perder foco). */
  flush = (id: string): void => {
    this.clearTimer(id)
    void this.run(id)
  }

  /** Escape: vuelve al último texto guardado. En conflicto no hace nada. */
  revert = (id: string): void => {
    const current = this.drafts.get(id)
    if (!current || current.status === 'conflict') {
      return
    }
    this.clearTimer(id)
    // Si hay un PUT en vuelo, al terminar se reenvía el texto revertido.
    this.put(id, {
      base: current.base,
      text: current.base.text,
      status: this.inflight.has(id) ? 'saving' : 'saved',
    })
  }

  /** Reintenta tras un error de red o de validación. */
  retry = (id: string): void => {
    if (this.drafts.get(id)?.status === 'error') {
      void this.run(id)
    }
  }

  retryAll = (): void => {
    for (const id of [...this.drafts.keys()]) {
      this.retry(id)
    }
  }

  /** Conflicto: "Usar mi versión" reintenta sobre la revisión del servidor. */
  keepMine = (id: string): void => {
    const current = this.drafts.get(id)
    if (current?.status !== 'conflict' || !current.conflict) {
      return
    }
    this.put(id, { base: current.conflict, text: current.text, status: 'dirty' })
    void this.run(id)
  }

  /** Conflicto: "Descartar" toma la versión del servidor. */
  discard = (id: string): void => {
    const current = this.drafts.get(id)
    if (current?.status !== 'conflict' || !current.conflict) {
      return
    }
    this.put(id, {
      base: current.conflict,
      text: current.conflict.text,
      status: 'saved',
    })
  }

  private clearTimer(id: string): void {
    const timer = this.timers.get(id)
    if (timer !== undefined) {
      clearTimeout(timer)
      this.timers.delete(id)
    }
  }

  private put(id: string, draft: SegmentDraft): void {
    this.drafts.set(id, draft)
    let next: AggregateStatus = 'saved'
    for (const status of PRIORITY) {
      if ([...this.drafts.values()].some((entry) => entry.status === status)) {
        next = status
        break
      }
    }
    this.aggregate = next
    this.listeners.forEach((listener) => {
      listener()
    })
  }

  private async run(id: string): Promise<void> {
    // Un solo PUT en vuelo por segmento; al terminar se reevalúa el último texto.
    while (!this.inflight.has(id)) {
      const draft = this.drafts.get(id)
      if (!draft || draft.status === 'conflict') {
        return
      }
      if (draft.text === draft.base.text) {
        this.put(id, { base: draft.base, text: draft.text, status: 'saved' })
        return
      }

      const sent = draft.text
      this.inflight.add(id)
      this.put(id, { base: draft.base, text: sent, status: 'saving' })

      try {
        const saved = await updateSegment(id, {
          text: sent,
          revision: draft.base.revision,
        })
        this.inflight.delete(id)
        const latest = this.drafts.get(id)?.text ?? sent
        // Si hubo cambios durante el vuelo, el bucle envía solo el último.
        this.put(id, {
          base: saved,
          text: latest === sent ? saved.text : latest,
          status: latest === sent ? 'saved' : 'dirty',
        })
        if (latest === sent) {
          return
        }
        this.clearTimer(id)
      } catch (error) {
        this.inflight.delete(id)
        const latest = this.drafts.get(id)?.text ?? sent
        if (error instanceof SegmentConflictError) {
          this.put(id, {
            base: draft.base,
            text: latest,
            status: 'conflict',
            conflict: error.current,
          })
        } else {
          this.put(id, {
            base: draft.base,
            text: latest,
            status: 'error',
            errorMessage:
              error instanceof Error
                ? error.message
                : translate('err.segment.save'),
          })
        }
        return
      }
    }
  }
}

export function useSegmentDrafts(): SegmentDraftStore {
  const [store] = useState(() => new SegmentDraftStore())
  const pending = useSyncExternalStore(store.subscribe, store.hasPending)

  useEffect(() => {
    if (!pending) {
      return
    }
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => {
      window.removeEventListener('beforeunload', warn)
    }
  }, [pending])

  return store
}
