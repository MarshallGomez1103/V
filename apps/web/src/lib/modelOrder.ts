/** Orden fijo del catálogo (de más capaz/recomendado a más pequeño). */
export const MODEL_ORDER: readonly string[] = [
  'turbo',
  'large-v3',
  'medium',
  'small',
  'base',
  'tiny',
]

function rank(modelId: string): number {
  const index = MODEL_ORDER.indexOf(modelId)
  return index === -1 ? MODEL_ORDER.length : index
}

/** Comparador por catálogo; los modelos desconocidos van al final, estables entre sí. */
export function compareModelIds(a: string, b: string): number {
  return rank(a) - rank(b)
}
