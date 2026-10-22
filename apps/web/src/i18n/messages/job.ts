import type { Catalog } from '../messages'

export const job = {
  'job.title.none': ['Sin transcripción', 'No transcription'],
  'job.title.creating': ['Creando la transcripción…', 'Creating the transcription…'],
  'job.creating.desc': [
    'Enviando la grabación al motor local…',
    'Sending the recording to the local engine…',
  ],
  'job.empty': [
    'Elige una grabación y una opción para empezar.',
    'Choose a recording and an option to start.',
  ],

  'job.state.QUEUED': ['En cola, esperando turno', 'Queued, waiting for its turn'],
  'job.state.PROBING': ['Analizando el archivo', 'Analyzing the file'],
  'job.state.PREPROCESSING': ['Preparando el audio', 'Preparing the audio'],
  'job.state.TRANSCRIBING': ['Transcribiendo el audio', 'Transcribing the audio'],
  'job.state.ALIGNING': ['Alineando palabras', 'Aligning words'],
  'job.state.DIARIZING': ['Identificando hablantes', 'Identifying speakers'],
  'job.state.MERGING': ['Uniendo resultados', 'Merging results'],
  'job.state.PERSISTING': ['Guardando la transcripción', 'Saving the transcript'],
  'job.state.COMPLETED': ['Transcripción completada', 'Transcription complete'],
  'job.state.FAILED': ['La transcripción falló', 'The transcription failed'],
  'job.state.CANCELLING': ['Cancelando la transcripción', 'Cancelling the transcription'],
  'job.state.CANCELLED': ['Transcripción cancelada', 'Transcription cancelled'],

  // Qué está pasando, en lenguaje humano
  'job.say.QUEUED': [
    'La transcripción está en cola y empezará en cuanto el motor quede libre.',
    'The transcription is queued and will start as soon as the engine is free.',
  ],
  'job.say.PROBING': [
    'Leyendo el archivo para conocer su duración y su formato.',
    'Reading the file to learn its duration and format.',
  ],
  'job.say.PREPROCESSING': [
    'Convirtiendo el audio al formato que usa el motor.',
    'Converting the audio to the format the engine uses.',
  ],
  'job.say.TRANSCRIBING': [
    'El motor está transcribiendo. El texto aparece abajo a medida que lo confirma.',
    'The engine is transcribing. The text appears below as it confirms it.',
  ],
  'job.say.TRANSCRIBING.pct': [
    'El motor está transcribiendo, va por el {pct} % del audio. El texto aparece abajo a medida que lo confirma.',
    'The engine is transcribing, {pct}% of the audio so far. The text appears below as it confirms it.',
  ],
  'job.say.ALIGNING': [
    'Alineando cada palabra con el audio para poder saltar a ella con un clic.',
    'Aligning each word with the audio so you can jump to it with a click.',
  ],
  'job.say.DIARIZING': [
    'Identificando quién habla en cada momento de la grabación.',
    'Working out who is speaking at each moment of the recording.',
  ],
  'job.say.DIARIZING.text': [
    'El texto ya está completo y puedes leerlo abajo. Se están identificando los hablantes; se rellenarán solos cuando termine.',
    'The text is already complete and you can read it below. Speakers are being identified; they fill in on their own when it finishes.',
  ],
  'job.say.MERGING': [
    'Uniendo el texto con los hablantes.',
    'Merging the text with the speakers.',
  ],
  'job.say.PERSISTING': [
    'Guardando la transcripción en este equipo.',
    'Saving the transcript on this computer.',
  ],
  'job.say.COMPLETED': ['La transcripción está lista.', 'The transcript is ready.'],
  'job.say.CANCELLING': [
    'Deteniendo el trabajo; la grabación original no se toca.',
    'Stopping the job; the original recording is not touched.',
  ],

  // Etapas del indicador
  'job.stages': ['Etapas', 'Stages'],
  'job.stage.prepare': ['Preparando', 'Preparing'],
  'job.stage.transcribe': ['Transcribiendo', 'Transcribing'],
  'job.stage.speakers': ['Hablantes', 'Speakers'],
  'job.stage.finish': ['Guardando', 'Saving'],
  'job.stage.state.done': ['Listo', 'Done'],
  'job.stage.state.pending': ['Pendiente', 'Pending'],
  'job.stage.state.waiting': ['En cola', 'Queued'],
  'job.stage.state.working': ['En curso', 'Working'],
  'job.stage.state.failed': ['Con error', 'Failed'],

  'job.progress.total': ['Progreso total', 'Overall progress'],
  'job.progress.pct': ['{pct} %', '{pct}%'],
  'job.progress.stagePct': ['{pct} % de la etapa', '{pct}% of this stage'],

  'job.fig.elapsed': ['Transcurrido', 'Elapsed'],
  'job.fig.remaining': ['Restante estimado', 'Estimated remaining'],
  'job.fig.stage': ['En esta etapa', 'In this stage'],
  'job.fig.total': ['Duración del trabajo', 'Job duration'],
  'job.fig.model': ['Modelo', 'Model'],
  'job.fig.device': ['Dispositivo', 'Device'],
  'job.fig.profile': ['Perfil', 'Profile'],
  'job.remaining.value': ['≈ {time}', '≈ {time}'],
  'job.remaining.unknown': ['Calculando…', 'Working it out…'],
  'job.remaining.soon': ['Casi listo', 'Almost done'],
  'job.remaining.late': ['Algo más de lo estimado', 'A bit longer than estimated'],
  'job.remaining.hint': [
    'Es una estimación a partir del ritmo actual; puede cambiar durante el trabajo.',
    'This is an estimate based on the current pace; it can change while the job runs.',
  ],
  'job.elapsed.hint': [
    'Tiempo desde que empezó el trabajo; avanza cada segundo.',
    'Time since the job started; it advances every second.',
  ],
  'job.device.hint': [
    'Dónde corre el motor: la tarjeta gráfica (GPU) o el procesador (CPU).',
    'Where the engine runs: the graphics card (GPU) or the processor (CPU).',
  ],

  'job.cancel': ['Cancelar', 'Cancel'],
  'job.cancel.why': [
    'Detiene el trabajo. La grabación original se conserva.',
    'Stops the job. The original recording is kept.',
  ],
  'job.adjust': ['Ajustar y repetir', 'Adjust and repeat'],
  'job.adjust.why': [
    'Vuelve a la configuración con la misma grabación para transcribir de nuevo.',
    'Goes back to the settings with the same recording so you can transcribe again.',
  ],

  'job.cloud.running': [
    'Tu audio se envía a {provider} mientras dura esta transcripción.',
    'Your audio is sent to {provider} while this transcription runs.',
  ],
  'job.cloud.done': [
    'Esta transcripción usó {provider} (cloud): tu audio salió de tu equipo.',
    'This transcription used {provider} (cloud): your audio left your computer.',
  ],

  'job.fail.generic': ['La transcripción falló.', 'The transcription failed.'],
  'job.fail.code': ['La transcripción falló (código {code}).', 'The transcription failed (code {code}).'],
  'job.fail.media_unreadable': ['No se pudo leer la grabación.', 'The recording could not be read.'],
  'job.fail.provider_unavailable': [
    'El motor de transcripción no está disponible.',
    'The transcription engine is not available.',
  ],
  'job.fail.model_missing': [
    'El modelo elegido no está instalado en este equipo.',
    'The chosen model is not installed on this computer.',
  ],
  'job.fail.out_of_memory': [
    'El equipo se quedó sin memoria durante la transcripción.',
    'The computer ran out of memory during the transcription.',
  ],
  'job.fail.timeout': [
    'La transcripción tardó demasiado y se detuvo.',
    'The transcription took too long and was stopped.',
  ],
  'job.fail.cloud_consent_expired': [
    'La transcripción se detuvo porque V se reinició: el permiso para enviar a la nube vale solo para una ejecución. Vuelve a lanzarla y confirma de nuevo.',
    'The transcription stopped because V restarted: the permission to send data to the cloud only lasts for one run. Launch it again and confirm again.',
  ],
  'job.cancelled.note': [
    'Cancelaste esta transcripción. La grabación original sigue intacta.',
    'You cancelled this transcription. The original recording is intact.',
  ],
  'job.diarFailed.title': [
    'No se pudo separar a los hablantes',
    'Speakers could not be separated',
  ],
  'job.diarFailed.body': [
    '({code}); la transcripción está completa.',
    '({code}); the transcript is complete.',
  ],

  // Vista previa en vivo
  'preview.title': ['Texto en vivo', 'Live text'],
  'preview.desc': [
    'Segmentos confirmados por el motor mientras transcribe; el resultado final puede ajustarse al terminar.',
    'Segments the engine has confirmed while it transcribes; the final result may be adjusted when it finishes.',
  ],
  'preview.empty': [
    'Aún no hay texto. Aparecerá aquí en cuanto el motor confirme los primeros segmentos.',
    'No text yet. It will show up here as soon as the engine confirms the first segments.',
  ],
  'preview.waiting': ['Esperando los primeros segmentos…', 'Waiting for the first segments…'],
  'preview.count_one': ['{n} segmento hasta {time}', '{n} segment up to {time}'],
  'preview.count_other': ['{n} segmentos hasta {time}', '{n} segments up to {time}'],
  'preview.list': ['Segmentos en vivo', 'Live segments'],
} as const satisfies Catalog
