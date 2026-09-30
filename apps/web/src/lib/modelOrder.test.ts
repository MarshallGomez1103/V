import { describe, expect, it } from 'vitest'

import { compareModelIds } from './modelOrder'

describe('compareModelIds', () => {
  it('ordena por catálogo y deja los desconocidos al final sin reordenarlos', () => {
    const ids = ['tiny', 'zeta', 'medium', 'alfa', 'turbo', 'base', 'large-v3', 'small']

    expect([...ids].sort(compareModelIds)).toEqual([
      'turbo',
      'large-v3',
      'medium',
      'small',
      'base',
      'tiny',
      'zeta',
      'alfa',
    ])
  })
})
