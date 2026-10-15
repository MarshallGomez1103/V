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
  'speak.cloud.title': ['Síntesis remota', 'Remote synthesis'],
  'speak.cloud.notice': [
    'Al escuchar una muestra o generar audio, el texto se enviará fuera de este equipo al proveedor seleccionado.',
    'When you hear a sample or generate audio, the text will be sent outside this computer to the selected provider.',
  ],
  'speak.cloud.confirm': [
    'Permitir el envío de texto a este modelo remoto para muestras y generación de audio.',
    'Allow sending text to this remote model for samples and audio generation.',
  ],
  'speak.cloud.result': [
    'Este trabajo usa un proveedor remoto que procesa el texto fuera de este equipo.',
    'This job uses a remote provider that processes the text outside this computer.',
  ],
  'speak.voice.description': [
    'Instalado: {models} modelos · {voices} voces',
    'Installed: {models} models · {voices} voices',
  ],
  'speak.voice.model': ['Modelo', 'Model'],
  'speak.voice.voice': ['Voz', 'Voice'],
  'speak.voice.language': ['Idioma', 'Language'],
  'speak.voice.speed': ['Velocidad', 'Speed'],
  'speak.voice.languages': ['Idiomas: {list}', 'Languages: {list}'],
  'speak.voice.notReady': [
    'El motor de este modelo no está listo en este equipo. Revisa Modelos.',
    'This model\'s engine is not ready on this computer. Check Models.',
  ],
  'speak.voice.speedValue': ['{speed}×', '{speed}×'],
  'speak.voice.speedHint': [
    'De {min}× (más lenta) a {max}× (más rápida). Cambia el ritmo de la voz al generar.',
    'From {min}× (slower) to {max}× (faster). It changes the pace of the voice when generating.',
  ],
  'speak.voice.speedReset': ['Velocidad normal (1×)', 'Normal speed (1×)'],

  'speak.sample': ['Escuchar muestra', 'Hear a sample'],
  'speak.sample.preparing': ['Preparando la muestra…', 'Preparing the sample…'],
  'speak.sample.playing': ['Reproduciendo la muestra', 'Playing the sample'],
  'speak.sample.cancel': ['Cancelar muestra', 'Cancel sample'],
  'speak.sample.stop': ['Detener muestra', 'Stop sample'],
  'speak.sample.hint': [
    'Reproduce solo la primera frase (hasta {max} caracteres), o una frase de prueba si aún no hay texto.',
    'Plays only the first sentence (up to {max} characters), or a test phrase if there is no text yet.',
  ],
  'speak.sample.blocked': [
    'El navegador bloqueó la reproducción automática. Pulsa «Escuchar muestra» otra vez.',
    'The browser blocked autoplay. Press "Hear a sample" again.',
  ],
  'speak.sample.failed': ['No se pudo preparar la muestra', 'Could not prepare the sample'],
  'speak.sample.text.es': ['Hola, esta es una muestra de mi voz.', 'Hola, esta es una muestra de mi voz.'],
  'speak.sample.text.en': [
    'Hello, this is a short sample of my voice.',
    'Hello, this is a short sample of my voice.',
  ],
  'speak.sample.text.fr': [
    'Bonjour, ceci est un court échantillon de ma voix.',
    'Bonjour, ceci est un court échantillon de ma voix.',
  ],
  'speak.sample.text.it': [
    'Ciao, questo è un breve campione della mia voce.',
    'Ciao, questo è un breve campione della mia voce.',
  ],
  'speak.sample.text.pt': [
    'Olá, esta é uma pequena amostra da minha voz.',
    'Olá, esta é uma pequena amostra da minha voz.',
  ],
  'speak.sample.text.zh': ['你好，这是我的声音样本。', '你好，这是我的声音样本。'],
  'speak.sample.text.ja': [
    'こんにちは、これは私の声のサンプルです。',
    'こんにちは、これは私の声のサンプルです。',
  ],
  'speak.sample.text.hi': [
    'नमस्ते, यह मेरी आवाज़ का एक छोटा नमूना है।',
    'नमस्ते, यह मेरी आवाज़ का एक छोटा नमूना है।',
  ],

  'speak.generate': ['Generar audio', 'Generate audio'],
  'speak.generate.creating': ['Enviando…', 'Sending…'],
  'speak.generate.needText': [
    'Escribe un texto para poder generar el audio.',
    'Type some text to be able to generate the audio.',
  ],

  'speak.result.title': ['Audio generado', 'Generated audio'],
  'speak.state.QUEUED': ['En cola, esperando turno', 'Queued, waiting for its turn'],
  'speak.state.RUNNING': ['Sintetizando la voz', 'Synthesizing the voice'],
  'speak.state.PERSISTING': ['Guardando el audio', 'Saving the audio'],
  'speak.state.COMPLETED': ['Audio listo', 'Audio ready'],
  'speak.state.FAILED': ['La generación falló', 'The generation failed'],
  'speak.state.CANCELLING': ['Cancelando la generación', 'Cancelling the generation'],
  'speak.state.CANCELLED': ['Generación cancelada', 'Generation cancelled'],
  'speak.say.QUEUED': [
    'Esperando a que termine otro trabajo: V solo hace una tarea pesada a la vez.',
    'Waiting for another job to finish: V runs only one heavy task at a time.',
  ],
  'speak.say.RUNNING': [
    'El motor está sintetizando el texto por fragmentos.',
    'The engine is synthesizing the text in chunks.',
  ],
  'speak.say.PERSISTING': [
    'Voz lista; se está guardando el archivo de audio.',
    'Voice rendered; the audio file is being saved.',
  ],
  'speak.say.COMPLETED': ['El audio está listo para escuchar.', 'The audio is ready to listen to.'],
  'speak.say.CANCELLING': [
    'Cancelando: termina el fragmento en curso y se descarta.',
    'Cancelling: the current chunk finishes and the result is discarded.',
  ],
  'speak.say.CANCELLED': [
    'Cancelaste la generación. No se guardó audio.',
    'You cancelled the generation. No audio was saved.',
  ],
  'speak.progress.label': ['Progreso', 'Progress'],
  'speak.progress.chunks': [
    '{done} de {total} fragmentos · {pct} %',
    '{done} of {total} chunks · {pct}%',
  ],
  'speak.progress.pct': ['{pct} %', '{pct}%'],
  'speak.cancel': ['Cancelar', 'Cancel'],
  'speak.cancel.why': [
    'Detiene la generación y descarta el audio.',
    'Stops the generation and discards the audio.',
  ],
  'speak.reused': ['Resultado reutilizado', 'Result reused'],
  'speak.reused.body': [
    'Ya existía un audio idéntico (mismo texto, voz y velocidad), así que no se volvió a sintetizar.',
    'An identical audio already existed (same text, voice and speed), so it was not synthesized again.',
  ],
  'speak.download': ['Descargar WAV', 'Download WAV'],
  'speak.fig.duration': ['Duración', 'Duration'],
  'speak.fig.rate': ['Frecuencia', 'Sample rate'],
  'speak.fig.size': ['Tamaño', 'Size'],
  'speak.fig.voice': ['Voz', 'Voice'],
  'speak.fig.speed': ['Velocidad', 'Speed'],
  'speak.fig.rateValue': ['{khz} kHz', '{khz} kHz'],
  'speak.fig.sizeValue': ['{mb} MB', '{mb} MB'],
  'speak.events.retry': ['Reconectar', 'Reconnect'],

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
  // Códigos de fallo del trabajo (`error_code` de una síntesis FAILED)
  'err.synth.voice_not_found': [
    'La voz elegida ya no existe en ese modelo.',
    'The chosen voice no longer exists in that model.',
  ],
  'err.synth.model_not_installed': [
    'El modelo de voz no está instalado: instálalo en Modelos.',
    'The voice model is not installed: install it in Models.',
  ],
  'err.synth.runtime_unavailable': [
    'El motor de voz no pudo ejecutar ese modelo. Revisa Modelos.',
    'The speech engine could not run that model. Check Models.',
  ],
  'err.synth.synthesis_failed': [
    'El motor no pudo sintetizar el texto. Prueba con otra voz o un texto más corto.',
    'The engine could not synthesize the text. Try another voice or a shorter text.',
  ],
  'err.synth.text_too_long': [
    'El texto es demasiado largo para este motor.',
    'The text is too long for this engine.',
  ],
  'err.synth.io_error': [
    'No se pudo guardar el audio en el disco.',
    'Could not save the audio to disk.',
  ],
  'err.synth.synthesis_internal_error': [
    'Error interno al generar el audio. Inténtalo de nuevo.',
    'Internal error while generating the audio. Try again.',
  ],
  'err.synth.synthesis_runner_crashed': [
    'El proceso de voz se cerró de forma inesperada. Inténtalo de nuevo.',
    'The speech process closed unexpectedly. Try again.',
  ],
  'err.synth.events_lost': [
    'Se perdió la conexión con el progreso de la generación.',
    'The connection to the generation progress was lost.',
  ],
  'err.synth.events_invalid': [
    'El servidor envió un estado de generación inválido.',
    'The server sent an invalid generation state.',
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
