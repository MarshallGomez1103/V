import type { Catalog } from '../messages'

export const trim = {
  'trim.title': ['Tramo a transcribir', 'Range to transcribe'],
  'trim.description': [
    'Elige dónde empieza y dónde termina lo que se transcribe; el resto del audio se omite.',
    'Choose where the transcribed part starts and ends; the rest of the audio is skipped.',
  ],
  'trim.start': ['Inicio', 'Start'],
  'trim.end': ['Fin', 'End'],
  'trim.startHere': ['Inicio aquí', 'Start here'],
  'trim.endHere': ['Fin aquí', 'End here'],
  'trim.play': ['Reproducir tramo', 'Play range'],
  'trim.clear': ['Quitar recorte', 'Clear trim'],
  'trim.whole': [
    'Se transcribe la grabación completa.',
    'The whole recording will be transcribed.',
  ],
  'trim.summary': [
    '{start}–{end} de {total} ({omitted} sin transcribir)',
    '{start}–{end} of {total} ({omitted} not transcribed)',
  ],
  'trim.job.label': ['Tramo transcrito', 'Transcribed range'],
  'trim.unknownDuration': [
    'No se conoce la duración de esta grabación, así que no se puede recortar. Se transcribirá completa.',
    'The duration of this recording is unknown, so it cannot be trimmed. It will be transcribed whole.',
  ],
  'trim.error.order': [
    'El fin debe ser posterior al inicio.',
    'The end must be after the start.',
  ],
  'trim.error.too_short': [
    'El tramo debe durar al menos 1 segundo.',
    'The range must be at least 1 second long.',
  ],
  'trim.error.out_of_range': [
    'El tramo queda fuera de la grabación.',
    'The range falls outside the recording.',
  ],
  'trim.blocked': ['Corrige el tramo para empezar.', 'Fix the range to start.'],
} as const satisfies Catalog
