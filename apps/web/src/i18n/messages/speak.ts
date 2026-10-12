import type { Catalog } from '../messages'

export const speak = {
  'speak.loading': ['Buscando las voces instaladas', 'Looking for installed voices'],
  'speak.error.title': ['No se pudieron cargar las voces', 'Could not load the voices'],

  'speak.empty.title': ['No hay voces instaladas', 'No voices installed'],
  'speak.empty.body': [
    'Instala un modelo de síntesis en Modelos para convertir texto en audio. Funciona sin conexión una vez instalado.',
    'Install a speech synthesis model in Models to turn text into audio. It works offline once installed.',
  ],
  'speak.empty.action': ['Ir a Modelos', 'Go to Models'],

  'speak.text.title': ['Texto', 'Text'],
  'speak.text.label': ['Texto a convertir en voz', 'Text to turn into speech'],
  'speak.text.placeholder': [
    'Escribe o pega aquí el texto que quieres escuchar.',
    'Type or paste the text you want to hear here.',
  ],
  'speak.counter': ['{chars} de {max} caracteres', '{chars} of {max} characters'],
  'speak.counter.words_one': ['1 palabra', '1 word'],
  'speak.counter.words_other': ['{n} palabras', '{n} words'],
  'speak.warn.near': [
    'Te acercas al límite: quedan {left} caracteres.',
    'You are close to the limit: {left} characters left.',
  ],
  'speak.over': [
    'El texto supera el límite por {over} caracteres. Acórtalo para poder generar el audio.',
    'The text is {over} characters over the limit. Shorten it to generate the audio.',
  ],
  'speak.clear': ['Borrar el texto', 'Clear the text'],

  'speak.voice.title': ['Voz', 'Voice'],
  'speak.voice.description': [
    'Instalado: {models} modelos · {voices} voces',
    'Installed: {models} models · {voices} voices',
  ],
  'speak.voice.model': ['Modelo', 'Model'],
  'speak.voice.voice': ['Voz', 'Voice'],
  'speak.voice.language': ['Idioma', 'Language'],
  'speak.voice.speed': ['Velocidad', 'Speed'],
  'speak.voice.soon': [
    'Aquí elegirás el modelo, la voz, el idioma y la velocidad, y podrás escuchar una muestra corta.',
    'Here you will pick the model, voice, language and speed, and be able to hear a short sample.',
  ],

  // Errores de la API de síntesis (`err.synth.<código estable>`)
  'err.synth.synthesis_provider_not_found': [
    'Ese motor de voz ya no está disponible.',
    'That speech engine is no longer available.',
  ],
  'err.synth.synthesis_model_unknown': [
    'El motor no conoce ese modelo de voz.',
    'The engine does not know that voice model.',
  ],
  'err.synth.synthesis_voice_not_found': [
    'Ese modelo no tiene la voz elegida.',
    'That model does not have the chosen voice.',
  ],
  'err.synth.synthesis_model_not_installed': [
    'El modelo de voz no está instalado: instálalo en Modelos.',
    'The voice model is not installed: install it in Models.',
  ],
  'err.synth.synthesis_runtime_unavailable': [
    'El motor de voz no puede ejecutar ese modelo ahora. Revisa Modelos.',
    'The speech engine cannot run that model right now. Check Models.',
  ],
  'err.synth.synthesis_request_invalid': [
    'El texto está vacío, supera el límite o la velocidad está fuera de rango.',
    'The text is empty, over the limit, or the speed is out of range.',
  ],
  'err.synth.synthesis_job_not_found': [
    'Esa generación ya no existe.',
    'That generation no longer exists.',
  ],
  'err.synth.synthesis_job_terminal': [
    'La generación ya había terminado.',
    'The generation had already finished.',
  ],
  'err.synth.synthesis_job_active': [
    'La generación sigue en curso: cancélala antes de borrarla.',
    'The generation is still running: cancel it before deleting it.',
  ],
  'err.synth.synthesis_audio_not_ready': [
    'El audio todavía no está listo.',
    'The audio is not ready yet.',
  ],
  'err.synth.synthesis_audio_missing': [
    'El archivo de audio ya no está en este equipo.',
    'The audio file is no longer on this computer.',
  ],
  'err.synth.synthesis_delete_forbidden': [
    'El borrado necesita confirmación desde la interfaz.',
    'Deleting needs confirmation from the interface.',
  ],
  'err.synth.synthesis_delete_failed': [
    'No se pudo borrar el audio. Inténtalo de nuevo.',
    'Could not delete the audio. Try again.',
  ],
  'err.synth.invalid_response': [
    'El servidor respondió algo que V no entiende. Reinicia V.',
    'The server answered something V does not understand. Restart V.',
  ],
  'err.synth.network_error': [
    'No se pudo conectar con el servidor.',
    'Could not connect to the server.',
  ],
  'err.synth.generic': [
    'No se pudo completar la operación de voz (código: {code}).',
    'The speech operation could not be completed (code: {code}).',
  ],
} as const satisfies Catalog
