import type { Catalog } from '../messages'

export const project = {
  'lib.project.named': ['Abrir proyecto {name}', 'Open project {name}'],
  'project.title': ['Proyecto', 'Project'],
  'project.description': [
    'Suma varias grabaciones al proyecto. V guarda una copia de cada una en su carpeta de datos y no modifica el original.',
    'Add several recordings to the project. V keeps a copy of each in its data folder and never changes the original.',
  ],
  'project.upload.title': ['Añadir grabaciones', 'Add recordings'],
  'project.drop': [
    'Suelta aquí tus audios o videos, o haz clic para elegirlos',
    'Drop your audio or video files here, or click to choose them',
  ],
  'project.upload.waiting': ['En espera', 'Waiting'],
  'project.upload.progress': ['Subiendo {pct} %', 'Uploading {pct} %'],
  'project.upload.failed': ['No se pudo importar {name}', 'Could not import {name}'],
  'project.recordings.title': ['Grabaciones', 'Recordings'],
  'project.recordings.table': ['Grabaciones del proyecto', 'Recordings of the project'],
  'project.count_one': ['{n} grabación', '{n} recording'],
  'project.count_other': ['{n} grabaciones', '{n} recordings'],
  'project.empty': [
    'Todavía no hay grabaciones en este proyecto.',
    'There are no recordings in this project yet.',
  ],
  'project.error.title': [
    'No se pudieron consultar las grabaciones',
    'Could not load the recordings',
  ],
  'err.project.invalid_recordings': [
    'La API devolvió una lista de grabaciones inválida.',
    'The API returned an invalid recording list.',
  ],
} as const satisfies Catalog
