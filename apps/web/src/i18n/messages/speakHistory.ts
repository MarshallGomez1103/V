import type { Catalog } from '../messages'

export const speakHistory = {
  'speak.history.title': ['Historial de voz', 'Speech history'],
  'speak.history.description': ['Generaciones recientes guardadas en este equipo.', 'Recent generations saved on this computer.'],
  'speak.history.loading': ['Cargando el historial…', 'Loading history…'],
  'speak.history.empty': ['Aún no hay generaciones guardadas.', 'No saved generations yet.'],
  'speak.history.error': ['No se pudo cargar el historial.', 'Could not load history.'],
  'speak.history.date': ['Fecha', 'Date'],
  'speak.history.play': ['Escuchar', 'Listen'],
  'speak.history.close': ['Cerrar reproductor', 'Close player'],
  'speak.history.confirm': ['¿Eliminar esta generación y su audio?', 'Delete this generation and its audio?'],
  'speak.history.delete': ['Confirmar: eliminar', 'Confirm: delete'],
  'speak.history.deleting': ['Eliminando generación…', 'Deleting generation…'],
  'speak.history.deleteError': ['No se pudo eliminar la generación. Inténtalo de nuevo.', 'Could not delete the generation. Try again.'],
} as const satisfies Catalog
