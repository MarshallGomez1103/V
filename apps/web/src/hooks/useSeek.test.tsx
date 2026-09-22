import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useSeek } from './useSeek'

describe('useSeek', () => {
  it('guarda el instante e incrementa el nonce en cada seek', () => {
    const { result } = renderHook(() => useSeek())
    expect(result.current.seekToMs).toBeNull()
    expect(result.current.seekNonce).toBe(0)

    act(() => {
      result.current.seek(1500)
    })
    expect(result.current.seekToMs).toBe(1500)
    expect(result.current.seekNonce).toBe(1)

    act(() => {
      result.current.seek(1500)
    })
    expect(result.current.seekNonce).toBe(2)
  })
})
