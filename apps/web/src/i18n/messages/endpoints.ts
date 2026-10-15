import type { Catalog } from '../messages'

/** Servidores compatibles con la API de OpenAI (V4-04). */
export const endpoints = {
  'ep.title': ['Servidores compatibles con OpenAI', 'OpenAI-compatible servers'],
  'ep.desc': [
    'Usa cualquier servidor de voz que hable la API de OpenAI: locales y gratuitos (LocalAI, speaches, Kokoro-FastAPI) o remotos con tu clave. Sus modelos aparecen en Transcribir y en Voz.',
    'Use any speech server that speaks the OpenAI API: local and free (LocalAI, speaches, Kokoro-FastAPI) or remote with your key. Their models show up in Transcribe and Voice.',
  ],
  'ep.loading': ['Consultando servidores…', 'Checking servers…'],
  'ep.empty': ['Aún no has añadido ningún servidor.', 'You have not added any server yet.'],
  'ep.add': ['Añadir servidor', 'Add server'],
  'ep.edit': ['Editar', 'Edit'],
  'ep.test': ['Probar conexión', 'Test connection'],
  'ep.delete.confirm': ['Confirmar: eliminar', 'Confirm: delete'],
  'ep.local': ['Local', 'Local'],
  'ep.form.new': ['Nuevo servidor', 'New server'],
  'ep.form.edit': ['Editar {name}', 'Edit {name}'],
  'ep.name': ['Nombre', 'Name'],
  'ep.url': ['URL base', 'Base URL'],
  'ep.url.help': [
    'Incluye /v1. Ejemplo: http://127.0.0.1:8880/v1',
    'Include /v1. Example: http://127.0.0.1:8880/v1',
  ],
  'ep.key': ['Clave de API (opcional)', 'API key (optional)'],
  'ep.key.keep': ['Deja vacío para conservar la clave guardada', 'Leave empty to keep the saved key'],
  'ep.key.none': ['Solo si el servidor la pide', 'Only if the server asks for one'],
  'ep.key.clear': ['Quitar la clave guardada', 'Remove the saved key'],
  'ep.key.saved': ['Clave guardada', 'Key saved'],
  'ep.stt': ['Modelos de transcripción', 'Transcription models'],
  'ep.tts': ['Modelos de voz', 'Speech models'],
  'ep.voices': ['Voces', 'Voices'],
  'ep.list.help': ['Separados por comas, tal como los nombra el servidor.', 'Comma separated, exactly as the server names them.'],
  'ep.none': ['ninguno', 'none'],
  'ep.cloud.title': ['Este servidor no está en tu equipo', 'This server is not on your computer'],
  'ep.cloud.body': [
    'El audio que transcribas y el texto que conviertas en voz con él se enviarán a {host}. V nunca lo usa como respaldo: solo cuando lo eliges.',
    'The audio you transcribe and the text you turn into speech with it will be sent to {host}. V never uses it as a fallback: only when you choose it.',
  ],
  'ep.cloud.consent': [
    'Entiendo que el audio y el texto saldrán de mi equipo hacia este servidor.',
    'I understand that audio and text will leave my computer for this server.',
  ],
  'ep.saved': ['Servidor guardado.', 'Server saved.'],
  'ep.deleted': ['Servidor eliminado.', 'Server deleted.'],
  'ep.test.ok': ['Conectado. Modelos que anuncia: {models}', 'Connected. Models it lists: {models}'],
  'ep.test.okEmpty': ['Conectado. El servidor no lista modelos.', 'Connected. The server lists no models.'],
  'ep.test.endpoint_unreachable': [
    'No se pudo conectar. ¿Está el servidor encendido y la URL bien escrita?',
    'Could not connect. Is the server running and the URL right?',
  ],
  'ep.test.endpoint_timeout': ['El servidor no respondió a tiempo.', 'The server did not answer in time.'],
  'ep.test.endpoint_auth_rejected': ['El servidor rechazó la clave.', 'The server rejected the key.'],
  'ep.test.endpoint_models_unlisted': [
    'El servidor responde, pero no lista modelos (/models). Puede funcionar igual.',
    'The server answers but does not list models (/models). It may still work.',
  ],
  'ep.test.endpoint_http_error': ['El servidor respondió con un error ({status}).', 'The server answered with an error ({status}).'],

  'err.provider.endpoint_invalid': [
    'Revisa los datos: URL http(s) sin usuario ni parámetros, al menos un modelo y, si hay modelos de voz, al menos una voz.',
    'Check the data: an http(s) URL without user or parameters, at least one model and, with speech models, at least one voice.',
  ],
  'err.provider.endpoint_cloud_consent_required': [
    'Este servidor está fuera de tu equipo: confirma que aceptas enviarle audio y texto.',
    'This server is outside your computer: confirm that you accept sending it audio and text.',
  ],
  'err.provider.endpoint_not_found': ['Ese servidor ya no existe.', 'That server no longer exists.'],
  'err.provider.endpoints_file_insecure': [
    'El archivo de servidores de V no es seguro (debe tener permisos 0600). Corrige sus permisos y reintenta.',
    'The V servers file is not safe (it must have 0600 permissions). Fix its permissions and retry.',
  ],
  'err.provider.endpoints_file_invalid': [
    'No se pudo leer el archivo de servidores de V. Revísalo o bórralo y reintenta.',
    'Could not read the V servers file. Check it or delete it and retry.',
  ],
  'err.provider.endpoints_write_failed': [
    'No se pudo guardar el servidor en el disco. Revisa los permisos y el espacio.',
    'Could not save the server to disk. Check permissions and space.',
  ],
  'err.provider.endpoint_test_unavailable': [
    'La prueba de conexión no está disponible.',
    'The connection test is not available.',
  ],
} as const satisfies Catalog
