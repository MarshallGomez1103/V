import type { Catalog } from '../messages'

export const transcribe = {
  // Importar
  'import.title': ['Importar grabación', 'Import a recording'],
  'import.description': [
    'El original no se modifica; todo se procesa en este equipo.',
    'The original is never modified; everything is processed on this computer.',
  ],
  'import.drop': [
    'Suelta aquí tu audio o video, o haz clic para elegir un archivo',
    'Drop your audio or video here, or click to choose a file',
  ],
  'import.formats': [
    'Audio o video: si FFmpeg lo reconoce, VOZ lo importa.',
    'Audio or video: if FFmpeg recognizes it, VOZ can import it.',
  ],
  'import.removeFile': ['Quitar archivo', 'Remove file'],
  'import.fileReady': ['Archivo listo · {size}', 'File ready · {size}'],
  'import.multiple': [
    'Solo se importa un archivo a la vez; se tomó "{name}".',
    'Only one file is imported at a time; "{name}" was used.',
  ],
  'import.projectName': ['Nombre del proyecto', 'Project name'],
  'import.projectName.help': [
    'Agrupa la grabación, su glosario y sus transcripciones.',
    'Groups the recording, its glossary and its transcripts.',
  ],
  'import.projectName.invalid': [
    'Escribe un nombre para el proyecto.',
    'Enter a name for the project.',
  ],
  'import.defaultName': ['Grabación {date}', 'Recording {date}'],
  'import.progress.label': ['Progreso de la importación', 'Import progress'],
  'import.creating': ['Creando proyecto…', 'Creating project…'],
  'import.uploading': ['Subiendo {pct} %', 'Uploading {pct}%'],
  'import.error.title': ['No se pudo importar', 'Could not import'],
  'import.submit': ['Crear proyecto e importar', 'Create project and import'],
  'import.submitting': ['Importando…', 'Importing…'],
  'import.submit.why': [
    'Elige un archivo para continuar.',
    'Choose a file to continue.',
  ],

  // Pasos iniciales (estado vacío)
  'start.title': ['Cómo empezar', 'Getting started'],
  'start.step1': [
    'Importa una grabación de audio o video.',
    'Import an audio or video recording.',
  ],
  'start.step2': [
    'Elige el motor, el perfil y, si quieres, separar hablantes.',
    'Pick the engine, the profile and, if you want, speaker separation.',
  ],
  'start.step3': [
    'Mira el texto aparecer, corrígelo y expórtalo.',
    'Watch the text appear, fix it and export it.',
  ],
  'start.models': [
    'Los motores se instalan una vez en la sección Modelos.',
    'Engines are installed once in the Models section.',
  ],
  'start.models.link': ['Ir a Modelos', 'Go to Models'],

  // Hablantes
  'diar.toggle': ['Detectar quién habla', 'Detect who is speaking'],
  'diar.off': ['Desactivado', 'Off'],
  'diar.on': ['Activado', 'On'],
  'diar.help.label': ['Cómo funciona la detección de hablantes', 'How speaker detection works'],
  'diar.help.1': [
    'Un segundo modelo separa la grabación por persona después de transcribir y asigna cada segmento a un hablante.',
    'A second model splits the recording by person after transcribing and assigns each segment to a speaker.',
  ],
  'diar.help.2': [
    'El texto no cambia. Los nombres se pueden editar después, y si los hablantes fallan, la transcripción queda completa.',
    'The text does not change. You can rename speakers afterwards, and if speaker detection fails the transcript is still complete.',
  ],
  'diar.count': ['Cantidad de hablantes', 'Number of speakers'],
  'diar.mode.auto': ['Automático', 'Automatic'],
  'diar.mode.exact': ['Exacto', 'Exact'],
  'diar.mode.range': ['Rango', 'Range'],
  'diar.mode.auto.hint': [
    'VOZ decide cuántas personas hay.',
    'VOZ decides how many people there are.',
  ],
  'diar.mode.exact.hint': [
    'Úsalo si sabes cuántas personas hablan: suele acertar más.',
    'Use it when you know how many people speak: it is usually more accurate.',
  ],
  'diar.mode.range.hint': [
    'Indica un mínimo y un máximo y VOZ elige dentro del rango.',
    'Give a minimum and a maximum and VOZ picks within the range.',
  ],
  'diar.exact.label': ['Número de hablantes', 'Number of speakers'],
  'diar.min': ['Mínimo', 'Minimum'],
  'diar.max': ['Máximo', 'Maximum'],
  'diar.increase': ['Aumentar el número', 'Increase the number'],
  'diar.decrease': ['Disminuir el número', 'Decrease the number'],
  'diar.model.checking': [
    'Comprobando el modelo de hablantes…',
    'Checking the speaker model…',
  ],
  'diar.model.ready': ['Modelo de hablantes instalado.', 'Speaker model installed.'],
  'diar.model.missing.title': [
    'Falta el modelo de hablantes',
    'The speaker model is missing',
  ],
  'diar.model.missing.body': [
    'Se descarga una sola vez ({size}) desde GitHub y después funciona sin conexión. Hasta entonces no se puede transcribir con hablantes.',
    'It downloads once ({size}) from GitHub and then works offline. Until then you cannot transcribe with speakers.',
  ],
  'diar.model.download': [
    'Descargar modelo de hablantes ({size})',
    'Download speaker model ({size})',
  ],
  'diar.model.downloading.label': [
    'Descarga del modelo de hablantes',
    'Speaker model download',
  ],
  'diar.model.queued': ['En cola…', 'Queued…'],
  'diar.model.downloading': [
    'Descargando: {pct} % ({done} de {total})',
    'Downloading: {pct}% ({done} of {total})',
  ],
  'diar.model.unavailable.title': [
    'El modelo de hablantes no se puede usar aquí',
    'The speaker model cannot be used here',
  ],
  'diar.model.unavailable.body': [
    'Esta instalación de VOZ no incluye el componente que lo ejecuta (extra «diarization»). Desactiva «Detectar quién habla» para transcribir.',
    'This VOZ installation does not include the component that runs it (the "diarization" extra). Turn off "Detect who is speaking" to transcribe.',
  ],
  'diar.model.error.title': [
    'No se pudo comprobar el modelo de hablantes',
    'Could not check the speaker model',
  ],
  'diar.blocked': [
    'Transcribir se activa cuando el modelo de hablantes esté instalado. También puedes desactivar «Detectar quién habla».',
    'Transcribe turns on once the speaker model is installed. You can also turn off "Detect who is speaking".',
  ],

  // Instrucciones de estilo (prompt)
  'style.label': ['Instrucciones de estilo (opcional)', 'Style instructions (optional)'],
  'style.help.label': ['Cómo funcionan las instrucciones de estilo', 'How style instructions work'],
  'style.help.1': [
    'Whisper no obedece órdenes como un chat. Si escribes «colócale comas», no hará nada.',
    'Whisper does not obey commands like a chat does. Writing "add commas" will do nothing.',
  ],
  'style.help.2': [
    'El texto que escribes se usa como contexto previo: el modelo imita su estilo, es decir, su puntuación, sus mayúsculas y su vocabulario.',
    'The text you write is used as prior context: the model imitates its style, that is, its punctuation, capitalization and vocabulary.',
  ],
  'style.help.3': [
    'Por eso lo que funciona es escribir un ejemplo bien puntuado, y mejor si trata del mismo tema que la grabación. No garantiza el resultado.',
    'So what works is writing a well-punctuated example, ideally on the same topic as the recording. It does not guarantee the result.',
  ],
  'style.placeholder': [
    'Ejemplo: Hola, buenas tardes. Hoy hablaremos del presupuesto, el calendario y los responsables, en ese orden.',
    'Example: Hello, good afternoon. Today we will talk about the budget, the schedule and the owners, in that order.',
  ],
  'style.helper': [
    'No es una orden: escribe un ejemplo del estilo que quieres (con comas y puntos).',
    'Not a command: write an example of the style you want (with commas and periods).',
  ],
  'style.example': [
    'Hola, buenas tardes. Hoy hablaremos del presupuesto, del calendario y de los responsables; primero, el presupuesto.',
    'Hello, good afternoon. Today we will talk about the budget, the schedule and the owners; first, the budget.',
  ],
  'style.useExample': ['Usar un ejemplo con puntuación', 'Use a punctuated example'],
  'style.clear': ['Borrar', 'Clear'],

  // Perfil de calidad
  'profile.legend': ['Perfil de calidad', 'Quality profile'],
  'profile.loading': ['Cargando perfiles…', 'Loading profiles…'],
  'profile.measured': ['Medido', 'Measured'],
  'profile.default.label': ['Estándar', 'Standard'],
  'profile.default.description': [
    'Valores por defecto del motor. Es lo que se usaba antes de existir perfiles.',
    'The engine defaults. This is what was used before profiles existed.',
  ],
  'profile.academic.label': ['Académico', 'Academic'],
  'profile.academic.description': [
    'Clases y charlas largas: no arrastra el texto previo, menos reintentos aleatorios y filtra silencios con VAD. Sin medición propia todavía.',
    'Lectures and long talks: does not carry the previous text, fewer random retries and filters silences with VAD. Not measured by VOZ yet.',
  ],
  'profile.vad.on': ['activado', 'on'],
  'profile.vad.off': ['apagado', 'off'],
  'profile.recommended': [
    'Hay un perfil recomendado, y solo porque existe una medición real.',
    'There is a recommended profile, and only because a real measurement exists.',
  ],
  'profile.synthetic': [
    'Orientativo: se midió con audio sintético.',
    'Indicative only: it was measured with synthetic audio.',
  ],
  'profile.noRecommendation': [
    'No hay perfil recomendado: falta una medición para este caso.',
    'No recommended profile: there is no measurement for this case.',
  ],
  'profile.evidence.label': ['Ver la evidencia', 'See the evidence'],
  'profile.tech': ['Detalles técnicos de cada perfil', 'Technical details of each profile'],
  'profile.scope': [
    'Solo afecta a Faster Whisper; whisper.cpp y los motores en la nube lo ignoran.',
    'Only affects Faster Whisper; whisper.cpp and cloud engines ignore it.',
  ],
  'term.beam': ['Beam', 'Beam'],
  'term.beam.def': [
    'Búsqueda por haz: cuántas alternativas explora el modelo en cada palabra. Más alternativas suele dar mejor texto y tarda más.',
    'Beam search: how many alternatives the model explores for each word. More alternatives usually gives better text and takes longer.',
  ],
  'term.vad': ['VAD', 'VAD'],
  'term.vad.def': [
    'Detección de actividad de voz: omite silencios y ruido antes de transcribir, lo que reduce frases inventadas en los silencios.',
    'Voice activity detection: skips silence and noise before transcribing, which reduces made-up sentences during silences.',
  ],
  'term.prevtext': ['Contexto previo', 'Previous context'],
  'term.prevtext.def': [
    'Si está activo, cada ventana de audio se transcribe con el texto anterior como contexto. Ayuda a la coherencia, pero un error o un bucle puede contagiarse.',
    'When on, each audio window is transcribed with the previous text as context. It helps coherence, but an error or a loop can spread.',
  ],
  'term.measured.def': [
    'Hay una medición real de error (WER) que respalda esta recomendación.',
    'A real error measurement (WER) backs this recommendation.',
  ],
  'common.yes': ['sí', 'yes'],
  'common.no': ['no', 'no'],

  // Términos técnicos (dispositivo, precisión, perfil de procesamiento)
  'term.device.cuda': ['GPU (CUDA)', 'GPU (CUDA)'],
  'term.device.cuda.def': [
    'Tarjeta gráfica NVIDIA usada con CUDA: transcribe mucho más rápido que el procesador.',
    'NVIDIA graphics card used through CUDA: transcribes much faster than the processor.',
  ],
  'term.device.cpu': ['CPU', 'CPU'],
  'term.device.cpu.def': [
    'El procesador del equipo: funciona en cualquier máquina, pero es más lento que una GPU.',
    'The computer processor: works on any machine, but is slower than a GPU.',
  ],
  'term.precision.float16.def': [
    'Números de 16 bits: rápido y casi sin pérdida de precisión en una GPU.',
    '16-bit numbers: fast and nearly lossless on a GPU.',
  ],
  'term.precision.float32.def': [
    'Números de 32 bits: máxima precisión, con más memoria y más lento.',
    '32-bit numbers: highest precision, with more memory and slower.',
  ],
  'term.precision.int8.def': [
    'Enteros de 8 bits (cuantización): usan menos memoria y corren más rápido en el procesador, con una pérdida de precisión pequeña.',
    '8-bit integers (quantization): use less memory and run faster on the processor, with a small loss of precision.',
  ],
  'term.precision.int8_float16.def': [
    'Mezcla de enteros de 8 bits y números de 16 bits: ahorra memoria en la GPU.',
    'A mix of 8-bit integers and 16-bit numbers: saves GPU memory.',
  ],
  'term.profile.fast': ['Rápido', 'Fast'],
  'term.profile.fast.def': [
    'Perfil de procesamiento que prioriza la velocidad y deja que el motor use la GPU si hay una.',
    'Processing profile that favors speed and lets the engine use the GPU when there is one.',
  ],
  'term.profile.quality': ['Calidad', 'Quality'],
  'term.profile.quality.def': [
    'Perfil de procesamiento que prioriza la precisión del texto, a costa de tiempo.',
    'Processing profile that favors text accuracy, at the cost of time.',
  ],

  // Selector de motor
  'opt.loading': ['Consultando los modelos de este equipo…', 'Checking the models on this computer…'],
  'opt.error.title': ['No se pudieron consultar las opciones', 'Could not load the options'],
  'opt.error.generic': [
    'No se pudieron consultar las opciones de transcripción.',
    'Could not load the transcription options.',
  ],
  'opt.none': ['No hay opciones de transcripción conocidas.', 'There are no known transcription options.'],
  'opt.legend': ['Modelo de transcripción', 'Transcription model'],
  'opt.recommended': ['Recomendado', 'Recommended'],
  'opt.recommended.def': [
    'El motor recomienda esta opción para este equipo según su hardware y el modelo instalado.',
    'The engine recommends this option for this computer, based on its hardware and the installed model.',
  ],
  'opt.sendsTo': ['Tu audio se enviará a {provider}', 'Your audio will be sent to {provider}'],
  'opt.model': ['Modelo', 'Model'],
  'opt.profile': ['Perfil', 'Profile'],
  'opt.profile.def': [
    'Perfil de procesamiento: decide si el motor prioriza velocidad o precisión y qué dispositivo prefiere.',
    'Processing profile: decides whether the engine favors speed or accuracy and which device it prefers.',
  ],
  'opt.execution': ['Ejecución', 'Execution'],
  'opt.execution.def': [
    'Dónde y con qué precisión numérica se ejecuta el modelo en este equipo.',
    'Where, and with what numeric precision, the model runs on this computer.',
  ],
  'opt.fallback': ['respaldo', 'fallback'],
  'opt.fallback.def': [
    'No se pudo usar el dispositivo preferido, así que se usa otro más lento.',
    'The preferred device could not be used, so a slower one is used instead.',
  ],
  'opt.installFirst': [
    'Instala un modelo para transcribir desde la sección «Modelos».',
    'Install a model to transcribe from the "Models" section.',
  ],
  'opt.goModels': ['Ir a Modelos', 'Go to Models'],
  'opt.goProviders': ['Ir a Proveedores cloud', 'Go to Cloud providers'],
  'opt.unavailable_one': ['Mostrar {n} motor no disponible', 'Show {n} unavailable engine'],
  'opt.unavailable_other': ['Mostrar {n} motores no disponibles', 'Show {n} unavailable engines'],
  'opt.noKey': ['Sin clave de {provider}.', 'No {provider} key.'],
  'opt.cloudNotice': ['Aviso de envío a la nube', 'Cloud upload notice'],
  'opt.cloudWarning': [
    'Tu audio se enviará a {provider} y saldrá de tu equipo.',
    'Your audio will be sent to {provider} and will leave this computer.',
  ],
  'opt.estimate': ['Costo estimado: {minutes} min · ≈ {usd} USD', 'Estimated cost: {minutes} min · ≈ {usd} USD'],
  'opt.estimate.error': ['No se pudo estimar el costo.', 'Could not estimate the cost.'],
  'opt.estimate.loading': ['Estimando el costo…', 'Estimating the cost…'],
  'opt.estimate.note': [
    'Tarifa de referencia del {date}, no verificada en vivo: tu factura real puede diferir.',
    'Reference rate from {date}, not verified live: your actual bill may differ.',
  ],
  'opt.consent': ['Entiendo que el audio sale de mi equipo', 'I understand the audio leaves my computer'],
  'opt.block.model_not_registered': ['Modelo no instalado', 'Model not installed'],
  'opt.block.model_files_missing': ['Faltan archivos del modelo', 'Model files are missing'],
  'opt.block.revision_unpinned': ['Revisión no fijada', 'Revision not pinned'],
  'opt.block.runtime_unavailable': ['Runtime Faster Whisper no instalado', 'Faster Whisper runtime not installed'],
  'opt.block.execution_unavailable': ['Sin dispositivo compatible', 'No compatible device'],
  'opt.block.transcription_unavailable': ['Transcripción no disponible', 'Transcription unavailable'],

  // Glosario
  'gloss.loading': ['Cargando glosario…', 'Loading glossary…'],
  'gloss.region': ['Editor de glosario', 'Glossary editor'],
  'gloss.label': ['Glosario del proyecto', 'Project glossary'],
  'gloss.placeholder': [
    'Un término por línea (nombres propios, siglas, vocabulario técnico)',
    'One term per line (proper names, acronyms, technical vocabulary)',
  ],
  'gloss.helper': [
    '{count} de {max} términos, hasta {length} caracteres cada uno. Ayuda al motor a acertar esas palabras; no cambia el texto transcrito.',
    '{count} of {max} terms, up to {length} characters each. It helps the engine get those words right; it does not change the transcribed text.',
  ],
  'gloss.tooMany': ['Hay demasiados términos (máximo {max}).', 'There are too many terms (maximum {max}).'],
  'gloss.tooLong': ['Algún término supera los {length} caracteres.', 'Some term is longer than {length} characters.'],
  'gloss.appliesTo': [
    'Lo usan: {engines}. Los demás motores lo ignoran.',
    'Used by: {engines}. Other engines ignore it.',
  ],
  'gloss.appliesNone': ['Ningún motor instalado usa el glosario.', 'No installed engine uses the glossary.'],
  'gloss.save': ['Guardar glosario', 'Save glossary'],
  'gloss.saving': ['Guardando…', 'Saving…'],
  'gloss.saved_one': ['Glosario guardado ({n} término).', 'Glossary saved ({n} term).'],
  'gloss.saved_other': ['Glosario guardado ({n} términos).', 'Glossary saved ({n} terms).'],

  // Trabajos recientes
  'recent.title': ['Transcripciones guardadas', 'Saved transcripts'],
  'recent.description': [
    'Todo lo que transcribiste queda en este equipo; ábrelo de nuevo cuando quieras.',
    'Everything you transcribed stays on this computer; open it again whenever you want.',
  ],
  'recent.loading': ['Buscando transcripciones guardadas…', 'Looking for saved transcripts…'],
  'recent.error.title': [
    'No se pudieron consultar las transcripciones guardadas',
    'Could not load the saved transcripts',
  ],
  'recent.error.generic': [
    'Reintenta; si el servidor se cerró, ábrelo de nuevo.',
    'Retry; if the server was closed, open it again.',
  ],
  'recent.empty': [
    'Todavía no hay transcripciones. Importa una grabación para empezar.',
    'There are no transcripts yet. Import a recording to get started.',
  ],
  'recent.open': ['Abrir', 'Open'],
  'recent.steps': ['Cómo empezar', 'Getting started'],

  // Configuración y arranque
  'cfg.engine.title': ['Motor y calidad', 'Engine and quality'],
  'cfg.engine.desc': [
    'Qué modelo transcribe y con qué receta.',
    'Which model transcribes and with what recipe.',
  ],
  'cfg.options.title': ['Opciones', 'Options'],
  'cfg.options.desc': [
    'Hablantes, estilo del texto y vocabulario de esta grabación.',
    'Speakers, text style and vocabulary for this recording.',
  ],
  'cfg.style': ['Instrucciones de estilo', 'Style instructions'],
  'cfg.glossary': ['Glosario del proyecto', 'Project glossary'],
  'cfg.start': ['Transcribir', 'Transcribe'],
  'cfg.starting': ['Creando…', 'Creating…'],
  'cfg.error.title': ['No se pudo crear la transcripción', 'Could not create the transcription'],
  'cfg.why.option': ['Elige un motor para poder transcribir.', 'Choose an engine to be able to transcribe.'],
  'cfg.why.consent': [
    'Marca que entiendes que el audio sale de tu equipo para continuar.',
    'Tick that you understand the audio leaves your computer to continue.',
  ],
  'work.mode.label': ['Modo de la transcripción', 'Transcript mode'],
  'work.mode.read': ['Leer', 'Read'],
  'work.mode.edit': ['Editar', 'Edit'],
  'work.pending.title': ['Identificando hablantes', 'Identifying speakers'],
  'work.pending.body': [
    'Ya puedes leer el texto; los hablantes se rellenan solos al terminar. Editar y exportar se activan entonces.',
    'You can already read the text; speakers fill in on their own when it finishes. Editing and exporting turn on then.',
  ],
  'work.playback.title': ['Reproducción', 'Playback'],
} as const satisfies Catalog
