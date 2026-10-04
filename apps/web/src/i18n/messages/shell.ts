import type { Catalog } from '../messages'

export const shell = {
  // Estructura general
  'app.name': ['VOZ', 'VOZ'],
  'app.title': ['VOZ · Transcripción local', 'VOZ · Local transcription'],
  'app.skip': ['Saltar al contenido', 'Skip to content'],

  'nav.sections': ['Secciones de VOZ', 'VOZ sections'],
  'nav.menu': ['Menú de secciones', 'Sections menu'],
  'nav.home': ['VOZ, ir al inicio', 'VOZ, go to the home page'],
  'nav.transcribir': ['Transcribir', 'Transcribe'],
  'nav.modelos': ['Modelos', 'Models'],
  'nav.proveedores': ['Proveedores cloud', 'Cloud providers'],

  'page.transcribir.title': ['Transcribir', 'Transcribe'],
  'page.transcribir.description': [
    'Importa una grabación, elige el motor y obtén texto editable. Todo se procesa en este equipo.',
    'Import a recording, pick an engine and get editable text. Everything is processed on this computer.',
  ],
  'page.modelos.title': ['Modelos', 'Models'],
  'page.modelos.description': [
    'Instala, reutiliza o elimina los modelos de este equipo. Funcionan sin Internet una vez instalados.',
    'Install, reuse or remove the models on this computer. They work offline once installed.',
  ],
  'page.proveedores.title': ['Proveedores cloud', 'Cloud providers'],
  'page.proveedores.description': [
    'Opcional. Solo si eliges un proveedor para una transcripción concreta, tu audio sale de este equipo.',
    'Optional. Your audio only leaves this computer if you pick a provider for a specific transcription.',
  ],

  // Idioma
  'lang.label': ['Idioma', 'Language'],
  'lang.es': ['Español', 'Español'],
  'lang.en': ['English', 'English'],

  // Apariencia
  'settings.label': ['Ajustes', 'Settings'],
  'appearance.design': ['Sistema de diseño', 'Design system'],
  'design.carbon': ['Carbon', 'Carbon'],
  'design.carbon.hint': [
    'IBM Carbon: esquinas rectas y colores planos. Es el diseño por defecto.',
    'IBM Carbon: square corners and flat colors. This is the default design.',
  ],
  'design.m3': ['Material 3', 'Material 3'],
  'design.m3.hint': [
    'Material Design 3 de Google: esquinas redondeadas, botones de píldora y colores derivados del acento. Solo cambia el aspecto, no las funciones.',
    'Google Material Design 3: rounded corners, pill buttons and colors derived from the accent. It only changes the look, not the features.',
  ],
  'appearance.theme': ['Tema', 'Theme'],
  'appearance.accent': ['Color de acento', 'Accent color'],
  'theme.system': ['Automático', 'Automatic'],
  'theme.system.hint': [
    'Sigue al sistema: Gray 100 si es oscuro, Gray 10 si es claro.',
    'Follows the system: Gray 100 when dark, Gray 10 when light.',
  ],
  'theme.white': ['White', 'White'],
  'theme.g10': ['Gray 10', 'Gray 10'],
  'theme.g90': ['Gray 90', 'Gray 90'],
  'theme.g100': ['Gray 100', 'Gray 100'],
  'accent.blue': ['Azul', 'Blue'],
  'accent.teal': ['Turquesa', 'Teal'],
  'accent.green': ['Verde', 'Green'],
  'accent.purple': ['Morado', 'Purple'],
  'accent.magenta': ['Magenta', 'Magenta'],
  'accent.red': ['Rojo', 'Red'],
  'accent.orange': ['Naranja', 'Orange'],
  'accent.neutral': ['Neutro', 'Neutral'],

  'shortcut.title': ['Icono de escritorio', 'Desktop icon'],
  'shortcut.create': ['Crear icono en el escritorio', 'Create desktop icon'],
  'shortcut.recreate': ['Volver a crearlo', 'Create it again'],
  'shortcut.help': [
    'Abre VOZ con un doble clic, sin buscar la carpeta.',
    'Opens VOZ with a double click, without finding the folder.',
  ],
  'shortcut.exists': [
    'Ya hay un icono en el escritorio.',
    'There is already an icon on the desktop.',
  ],
  'shortcut.created': ['Icono creado en el escritorio.', 'Icon created on the desktop.'],
  'shortcut.failed': [
    'No se pudo crear el icono. Inténtalo de nuevo.',
    'Could not create the icon. Try again.',
  ],

  'down.title': ['VOZ no responde', 'VOZ is not responding'],
  'down.body': [
    'No hay conexión con el servidor local. Si lo cerraste, ábrelo con el archivo Iniciar; esta página se reconecta sola. Tus datos siguen guardados en este equipo.',
    'There is no connection to the local server. If you closed it, open it with the Start file; this page reconnects on its own. Your data is still saved on this computer.',
  ],
  'down.retry': ['Reintentar ahora', 'Retry now'],

  // Cerrar servidor
  'shutdown.button': ['Cerrar servidor', 'Close server'],
  'shutdown.title': ['¿Cerrar VOZ?', 'Close VOZ?'],
  'shutdown.body': [
    'El servidor local se apaga y esta pestaña deja de responder. Tus grabaciones y transcripciones quedan guardadas.',
    'The local server shuts down and this tab stops responding. Your recordings and transcripts stay saved.',
  ],
  'shutdown.activeJob': [
    'Hay una transcripción en curso. Se detendrá y se reanudará al volver a abrir VOZ.',
    'A transcription is running. It will stop and resume when you open VOZ again.',
  ],
  'shutdown.confirm': ['Cerrar servidor', 'Close server'],
  'shutdown.cancel': ['Cancelar', 'Cancel'],
  'shutdown.closing': ['Cerrando…', 'Closing…'],
  'shutdown.close': ['Cerrar', 'Close'],
  'shutdown.failed': [
    'No se pudo cerrar desde aquí. Cierra la terminal donde se abrió VOZ (Ctrl+C).',
    'Could not close it from here. Close the terminal where VOZ was started (Ctrl+C).',
  ],
  'closed.title': ['VOZ se cerró', 'VOZ has closed'],
  'closed.body': [
    'Puedes cerrar esta pestaña. Para volver, abre el archivo Iniciar de la carpeta.',
    'You can close this tab. To come back, open the Start file in the folder.',
  ],
  'closed.doc': ['VOZ cerrado', 'VOZ closed'],

  // Estado de la API
  'health.offline.title': ['Sin conexión', 'No connection'],
  'health.offline.subtitle': [
    'Inicia el servidor local para conectar la interfaz.',
    'Start the local server to connect the interface.',
  ],
  'health.retry': ['Volver a comprobar', 'Check again'],
  'health.checking': [
    'Comprobando el servidor de este equipo…',
    'Checking the server on this computer…',
  ],
  'health.ok': ['Disponible', 'Available'],
  'health.ok.hint': [
    'El servidor local de VOZ respondió. Todo corre en este equipo (127.0.0.1).',
    'The local VOZ server answered. Everything runs on this computer (127.0.0.1).',
  ],
  'health.detail': ['API local · 127.0.0.1', 'Local API · 127.0.0.1'],

  // Términos con tooltip compartidos
  'term.cloud.def': [
    'Este motor envía tu audio a un servicio externo. Los motores locales nunca lo hacen.',
    'This engine sends your audio to an external service. Local engines never do.',
  ],

  // Genéricos
  'common.loading': ['Cargando', 'Loading'],
  'common.close': ['Cerrar', 'Close'],
  'common.cancel': ['Cancelar', 'Cancel'],
  'common.retry': ['Reintentar', 'Retry'],
  'common.save': ['Guardar', 'Save'],
  'common.delete': ['Eliminar', 'Delete'],
  'common.none': ['Ninguno', 'None'],
  'common.unknown': ['Desconocido', 'Unknown'],
  'common.notice.error': ['Error', 'Error'],
  'common.notice.info': ['Información', 'Information'],
  'common.notice.success': ['Correcto', 'Success'],
  'common.notice.warning': ['Advertencia', 'Warning'],
  'common.step.complete': ['Completada', 'Complete'],
  'common.step.incomplete': ['Pendiente', 'Pending'],
  'common.step.current': ['En curso', 'In progress'],
  'common.step.invalid': ['Con error', 'Failed'],
} as const satisfies Catalog
