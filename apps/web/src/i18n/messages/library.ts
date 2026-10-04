import type { Catalog } from '../messages'

/** v3: Home y biblioteca, espacio de trabajo por URL, exportar, audio y hablantes. */
export const library = {
  // Navegación
  'nav.inicio': ['Inicio', 'Home'],
  'nav.crumbs': ['Ruta de navegación', 'Breadcrumb'],

  // Home
  'page.inicio.title': ['Transcripciones', 'Transcripts'],
  'page.inicio.description': [
    'Todo lo que transcribiste queda en este equipo. Ábrelo, renómbralo o elimínalo.',
    'Everything you transcribed stays on this computer. Open it, rename it or delete it.',
  ],
  'lib.new': ['Nueva transcripción', 'New transcription'],
  'lib.table': ['Transcripciones guardadas', 'Saved transcripts'],
  'lib.count_one': ['{n} transcripción', '{n} transcript'],
  'lib.count_other': ['{n} transcripciones', '{n} transcripts'],
  'lib.search.label': ['Buscar transcripciones', 'Search transcripts'],
  'lib.search.placeholder': ['Buscar por nombre', 'Search by name'],
  'lib.search.clear': ['Limpiar búsqueda', 'Clear search'],
  'lib.noResults': ['Ninguna transcripción se llama «{query}».', 'No transcript is named “{query}”.'],
  'lib.col.name': ['Nombre', 'Name'],
  'lib.col.date': ['Fecha', 'Date'],
  'lib.col.duration': ['Duración', 'Duration'],
  'lib.col.state': ['Estado', 'Status'],
  'lib.col.speakers': ['Hablantes', 'Speakers'],
  'lib.col.actions': ['Acciones', 'Actions'],
  'lib.state.none': ['Sin transcribir', 'Not transcribed'],
  'lib.state.none.hint': [
    'Se importó el audio pero nunca se llegó a transcribir.',
    'The audio was imported but never transcribed.',
  ],
  'lib.model': ['Modelo: {model}', 'Model: {model}'],
  'lib.segments_one': ['{n} segmento', '{n} segment'],
  'lib.segments_other': ['{n} segmentos', '{n} segments'],
  'lib.open': ['Abrir', 'Open'],
  'lib.open.named': ['Abrir {name}', 'Open {name}'],
  'lib.rename': ['Renombrar', 'Rename'],
  'lib.rename.named': ['Renombrar {name}', 'Rename {name}'],
  'lib.delete': ['Eliminar', 'Delete'],
  'lib.delete.named': ['Eliminar {name}', 'Delete {name}'],
  'lib.loading': ['Cargando las transcripciones…', 'Loading the transcripts…'],
  'lib.empty': [
    'Todavía no hay transcripciones. Importa una grabación para empezar.',
    'There are no transcripts yet. Import a recording to get started.',
  ],
  'lib.error.title': [
    'No se pudieron consultar las transcripciones',
    'Could not load the transcripts',
  ],
  'lib.rename.title': ['Renombrar transcripción', 'Rename transcript'],
  'lib.rename.label': ['Nombre', 'Name'],
  'lib.rename.help': [
    'Solo cambia el nombre que ves en VOZ y el de los archivos que exportes.',
    'It only changes the name you see in VOZ and the name of the files you export.',
  ],
  'lib.rename.save': ['Guardar nombre', 'Save name'],
  'lib.rename.invalid': [
    'Escribe un nombre de 1 a 200 caracteres.',
    'Enter a name of 1 to 200 characters.',
  ],
  'lib.delete.title': ['Eliminar «{name}»', 'Delete “{name}”'],
  'lib.delete.body': [
    'Se borra de VOZ la transcripción con sus hablantes y la copia del audio que VOZ guardó para poder reproducirlo. Tu archivo original, el que elegiste desde tu equipo, no se toca. No se puede deshacer.',
    'This removes the transcript with its speakers and the copy of the audio that VOZ stored so it could play it. Your original file, the one you picked from your computer, is not touched. This cannot be undone.',
  ],
  'lib.delete.confirm': ['Eliminar para siempre', 'Delete permanently'],
  'lib.delete.error': ['No se pudo eliminar', 'Could not delete'],
  'lib.rename.error': ['No se pudo renombrar', 'Could not rename'],

  // Trabajo abierto por URL
  'work.loading': ['Abriendo la transcripción…', 'Opening the transcript…'],
  'work.notfound.title': ['No se encontró esta transcripción', 'This transcript was not found'],
  'work.notfound.body': [
    'Puede que se haya eliminado o que el enlace esté incompleto. Vuelve al inicio para ver las que hay.',
    'It may have been deleted or the link may be incomplete. Go back home to see the ones you have.',
  ],
  'work.notfound.back': ['Ir al inicio', 'Go home'],
  'work.crumb.home': ['Inicio', 'Home'],
  'work.adjust.title': ['Volver a transcribir', 'Transcribe again'],

  // Errores de proyecto
  'err.project.project_busy': [
    'Hay una transcripción en curso en este proyecto. Cancélala o espera a que termine.',
    'A transcription is running in this project. Cancel it or wait for it to finish.',
  ],
  'err.project.http_404': [
    'Esta versión de VOZ no admite esta acción todavía.',
    'This version of VOZ does not support this action yet.',
  ],
  'err.project.http_405': [
    'Esta versión de VOZ no admite esta acción todavía.',
    'This version of VOZ does not support this action yet.',
  ],

  // Exportar
  'exp.title': ['Exportar transcripción', 'Export transcript'],
  'exp.intro': [
    'Elige un formato, ajusta el texto y descarga el archivo. La vista previa muestra cómo quedará.',
    'Pick a format, adjust the text and download the file. The preview shows how it will look.',
  ],
  'exp.format': ['Formato', 'Format'],
  'exp.format.txt': ['Texto plano para pegar en cualquier parte.', 'Plain text to paste anywhere.'],
  'exp.format.markdown': [
    'Texto con formato, listo para notas o un documento.',
    'Formatted text, ready for notes or a document.',
  ],
  'exp.format.srt': [
    'Subtítulos con tiempos que leen casi todos los reproductores de video.',
    'Timed subtitles that almost every video player reads.',
  ],
  'exp.format.vtt': [
    'Subtítulos para la web (HTML5) y plataformas de video.',
    'Subtitles for the web (HTML5) and video platforms.',
  ],
  'exp.format.json': [
    'Todos los datos (segmentos, palabras, hablantes) para usarlos desde un programa.',
    'All the data (segments, words, speakers) for use from a program.',
  ],
  'exp.options': ['Opciones del texto', 'Text options'],
  'exp.timestamps.label': ['Incluir tiempos', 'Include timestamps'],
  'exp.timestamps.help': [
    'Pone al inicio de cada segmento el momento en que se dice, por ejemplo [00:01:23.000].',
    'Puts the moment it is said at the start of each segment, for example [00:01:23.000].',
  ],
  'exp.group.label': ['Agrupar por hablante', 'Group by speaker'],
  'exp.group.help': [
    'Junta lo que dice cada persona bajo su nombre. Cuando otra persona habla, empieza un grupo nuevo.',
    'Puts what each person says under their name. When someone else speaks, a new group starts.',
  ],
  'exp.options.na': [
    'Este formato ya trae sus propios tiempos y no admite estas opciones.',
    'This format already carries its own timing and does not take these options.',
  ],
  'exp.on': ['Sí', 'Yes'],
  'exp.off': ['No', 'No'],
  'exp.preview': ['Vista previa', 'Preview'],
  'exp.preview.loading': ['Preparando la vista previa…', 'Preparing the preview…'],
  'exp.preview.error': ['No se pudo preparar la vista previa.', 'Could not prepare the preview.'],
  'exp.preview.more': [
    'Solo se muestran las primeras líneas; el archivo trae todo el texto.',
    'Only the first lines are shown; the file contains the whole text.',
  ],
  'exp.download': ['Descargar {format}', 'Download {format}'],

  // Audio
  'audio.vol.label': ['Volumen: {percent} %', 'Volume: {percent} %'],
  'audio.vol.tip': [
    'Volumen del reproductor de VOZ, de 0 a 300 %. No cambia el volumen de tu equipo ni el archivo.',
    'Volume of the VOZ player, from 0 to 300 %. It does not change your computer volume or the file.',
  ],
  'audio.vol.warn': [
    'Por encima de 100 % el sonido puede saturarse. Úsalo solo con grabaciones muy bajas.',
    'Above 100 % the sound may distort. Use it only for very quiet recordings.',
  ],
  'audio.key.space': ['Espacio', 'Space'],
  'audio.rate.label': ['Velocidad', 'Speed'],
  'audio.rate.option': ['{rate}×', '{rate}×'],
  'audio.rate.normal': ['{rate}× (normal)', '{rate}× (normal)'],
  'audio.keys': [
    'Atajos: Espacio reproduce o pausa; ← y → mueven 5 s.',
    'Shortcuts: Space plays or pauses; ← and → move 5 s.',
  ],

  // Revisión
  'review.go': ['Ir a este segmento', 'Go to this segment'],
  'review.goCount': ['Ir al segmento por revisar', 'Go to the segment to review'],

  // Hablantes
  'spk.talk': ['Tiempo de habla de {name}', 'Speaking time of {name}'],
  'spk.talk.value': ['{time} · {percent} %', '{time} · {percent} %'],
  'spk.filter': ['Ver solo a {name} en la transcripción', 'Show only {name} in the transcript'],
  'spk.filter.off': ['Mostrar a todos en la transcripción', 'Show everyone in the transcript'],
  'spk.prev': ['Intervención anterior de {name}', 'Previous turn of {name}'],
  'spk.next': ['Intervención siguiente de {name}', 'Next turn of {name}'],
  'spk.sample': ['Escuchar una muestra de {name}', 'Listen to a sample of {name}'],
  'spk.filtering': ['Solo {name}', 'Only {name}'],
  'spk.filtering.clear': ['Mostrar a todos', 'Show everyone'],
  'spk.filtering.none': [
    'Este hablante no tiene segmentos en la transcripción.',
    'This speaker has no segments in the transcript.',
  ],
  'spk.recalc': ['Recalcular hablantes', 'Recompute speakers'],
  'spk.recalc.title': ['Recalcular hablantes', 'Recompute speakers'],
  'spk.recalc.body': [
    'Vuelve a separar quién habla, sin transcribir otra vez. El texto no cambia. Si VOZ reconoce a la misma persona, conserva el nombre que le pusiste.',
    'Separates who is speaking again without transcribing again. The text does not change. If VOZ recognises the same person, it keeps the name you gave them.',
  ],
  'spk.recalc.hint': [
    'Si salen más hablantes de los que hay, indica cuántos son o un máximo.',
    'If you get more speakers than there really are, say how many there are or give a maximum.',
  ],
  'spk.recalc.run': ['Recalcular', 'Recompute'],
  'spk.recalc.running': ['Recalculando hablantes…', 'Recomputing speakers…'],
  'spk.recalc.progress': ['Recalculando hablantes: {pct} %', 'Recomputing speakers: {pct} %'],
  'spk.recalc.done': ['Hablantes recalculados.', 'Speakers recomputed.'],
  'spk.recalc.failed': ['No se pudieron recalcular los hablantes', 'Could not recompute the speakers'],
  'spk.recalc.error': ['No se pudo iniciar el recálculo', 'Could not start the recomputation'],
  'spk.recalc.missing': [
    'Falta el modelo de hablantes. Instálalo en Modelos y vuelve a intentarlo.',
    'The speaker model is missing. Install it in Models and try again.',
  ],
  'spk.recalc.models': ['Ir a Modelos', 'Go to Models'],
} as const satisfies Catalog
