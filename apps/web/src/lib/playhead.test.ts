import { describe, expect, it, vi } from 'vitest'

import { createPlayhead } from './playhead'

describe('createPlayhead', () => {
  it('notifica solo cuando cambia el valor y permite darse de baja', () => {
    const playhead = createPlayhead()
    const listener = vi.fn()
    const unsubscribe = playhead.subscribe(listener)

    expect(playhead.get()).toBeUndefined()
    playhead.set(100)
    playhead.set(100)
    expect(playhead.get()).toBe(100)
    expect(listener).toHaveBeenCalledTimes(1)

    unsubscribe()
    playhead.set(200)
    expect(listener).toHaveBeenCalledTimes(1)
  })
})
