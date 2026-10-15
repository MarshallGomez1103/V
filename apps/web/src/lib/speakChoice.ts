import type { SynthesisModel, SynthesisOptions, SynthesisVoice } from '../api/synthesis'

/** Lo que el espectador eligió (parcial: lo que falte o ya no exista se resuelve contra las opciones). */
export interface SpeakPreference {
  model?: string
  voice?: string
  language?: string | null
  speed?: number
}

export interface SpeakChoice {
  model: SynthesisModel
  /** Voces del modelo para el idioma elegido. */
  voices: SynthesisVoice[]
  voice: SynthesisVoice | null
  /** Solo con un modelo de varios idiomas; con uno solo se envía `null`. */
  language: string | null
  speed: number
}

export const SPEED_STEP = 0.1
export const SAMPLE_MAX_CHARS = 120
const STORAGE_KEY = 'voz.speak.choice'

export const modelKey = (model: SynthesisModel): string => model.provider_id + ':' + model.model_id

/** `es-MX` -> `es`. */
const baseLanguage = (code: string): string => code.toLowerCase().split(/[-_]/u)[0] ?? ''

function voicesFor(model: SynthesisModel, language: string | null): SynthesisVoice[] {
  if (language === null) {
    return model.voices
  }
  const wanted = baseLanguage(language)
  const matching = model.voices.filter(
    (voice) => voice.languages.length === 0 || voice.languages.some((item) => baseLanguage(item) === wanted),
  )
  return matching.length > 0 ? matching : model.voices
}

/** Redondea al paso del control para que `0.30000000000000004` no llegue a la API ni a pantalla. */
export function roundSpeed(value: number): number {
  return Number((Math.round(value / SPEED_STEP) * SPEED_STEP).toFixed(2))
}

/**
 * Resuelve la elección contra las opciones actuales: modelo (el guardado, o el primero
 * listo), idioma (el guardado, o el de la interfaz si el modelo lo tiene), voz del idioma
 * y velocidad dentro del rango. Es pura, así que un modelo borrado cae solo en otro.
 */
export function resolveChoice(
  options: SynthesisOptions,
  preference: SpeakPreference,
  interfaceLanguage: string,
): SpeakChoice {
  const local = (item: SynthesisModel) =>
    !options.providers.some((provider) => provider.provider_id === item.provider_id && provider.locality === 'cloud')
  const model =
    options.models.find((item) => modelKey(item) === preference.model) ??
    options.models.find((item) => local(item) && item.runtime_ready) ??
    options.models.find(local) ??
    options.models.find((item) => item.runtime_ready) ??
    options.models[0]
  if (model === undefined) {
    throw new Error('resolveChoice needs at least one model')
  }
  const languages = model.languages
  const language =
    languages.length < 2
      ? null
      : (languages.find((item) => item === preference.language) ??
        languages.find((item) => baseLanguage(item) === interfaceLanguage) ??
        languages[0] ??
        null)
  const voices = voicesFor(model, language)
  const voice = voices.find((item) => item.id === preference.voice) ?? voices[0] ?? null
  const { min, max } = options.speed
  const speed = Math.min(max, Math.max(min, roundSpeed(preference.speed ?? 1)))
  return { model, voices, voice, language, speed }
}

export function loadPreference(): SpeakPreference {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    const parsed: unknown = raw === null ? null : JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null) {
      return {}
    }
    const data = parsed as Record<string, unknown>
    return {
      ...(typeof data.model === 'string' ? { model: data.model } : {}),
      ...(typeof data.voice === 'string' ? { voice: data.voice } : {}),
      ...(typeof data.language === 'string' || data.language === null
        ? { language: data.language }
        : {}),
      ...(typeof data.speed === 'number' && Number.isFinite(data.speed) ? { speed: data.speed } : {}),
    }
  } catch {
    return {}
  }
}

/** La elección ya resuelta, como preferencia (punto de partida de cada cambio). */
export function preferenceOf(choice: SpeakChoice): SpeakPreference {
  return {
    model: modelKey(choice.model),
    language: choice.language,
    speed: choice.speed,
    ...(choice.voice === null ? {} : { voice: choice.voice.id }),
  }
}

/** Preferencia del espectador, no crítica: si el almacenamiento falla, se ignora. */
export function savePreference(choice: SpeakChoice): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferenceOf(choice)))
  } catch {
    // Modo privado o almacenamiento bloqueado.
  }
}

/** Lo que se envía a `POST /api/synthesis` salvo el texto; `null` si falta la voz. */
export function requestOf(choice: SpeakChoice) {
  if (choice.voice === null) {
    return null
  }
  return {
    provider_id: choice.model.provider_id,
    model_id: choice.model.model_id,
    voice_id: choice.voice.id,
    language: choice.language,
    speed: choice.speed,
  }
}

const SENTENCE_END = /(?<=[.!?…。！？])\s+|\n+/u

/**
 * Primera oración del texto, con tope de `SAMPLE_MAX_CHARS` (cortada en un espacio si se
 * puede). Cadena vacía si no hay texto: el llamador usa entonces la frase fija del idioma.
 */
export function firstSentence(text: string): string {
  const first = text.trim().split(SENTENCE_END)[0]?.trim() ?? ''
  const chars = Array.from(first)
  if (chars.length <= SAMPLE_MAX_CHARS) {
    return first
  }
  const cut = chars.slice(0, SAMPLE_MAX_CHARS).join('')
  const space = cut.lastIndexOf(' ')
  return (space >= SAMPLE_MAX_CHARS / 2 ? cut.slice(0, space) : cut).trimEnd()
}

/** Idiomas con frase de prueba propia (`speak.sample.text.<código>`). */
export const SAMPLE_LANGUAGES = ['es', 'en', 'fr', 'it', 'pt', 'zh', 'ja', 'hi'] as const
export type SampleLanguage = (typeof SAMPLE_LANGUAGES)[number]

/** Idioma de la frase de prueba: el de la voz, el elegido o el primero del modelo; `en` si no hay frase. */
export function sampleLanguage(choice: SpeakChoice): SampleLanguage {
  const code = baseLanguage(
    choice.voice?.languages[0] ?? choice.language ?? choice.model.languages[0] ?? 'en',
  )
  return (SAMPLE_LANGUAGES as readonly string[]).includes(code) ? (code as SampleLanguage) : 'en'
}
