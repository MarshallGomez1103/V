import type { Catalog } from '../messages'

export const errors = {
  // Importación
  'err.upload.filename_invalid': ['El nombre del archivo no es válido.', 'The file name is not valid.'],
  'err.upload.project_not_found': ['El proyecto ya no existe.', 'The project no longer exists.'],
  'err.upload.media_too_large': ['El archivo supera el tamaño permitido.', 'The file exceeds the allowed size.'],
  'err.upload.media_unsupported': [
    'FFmpeg no reconoce este archivo como audio o video.',
    'FFmpeg does not recognize this file as audio or video.',
  ],
  'err.upload.media_corrupt': [
    'El archivo parece dañado o incompleto.',
    'The file looks damaged or incomplete.',
  ],
  'err.upload.media_storage_unavailable': [
    'No hay espacio o acceso al almacenamiento local.',
    'There is no space or access to local storage.',
  ],
  'err.upload.media_import_failed': [
    'La importación falló en el servidor local.',
    'The import failed on the local server.',
  ],
  'err.upload.network_error': [
    'No se pudo conectar con el servidor local.',
    'Could not connect to the local server.',
  ],
  'err.upload.aborted': ['La importación fue cancelada.', 'The import was cancelled.'],
  'err.upload.invalid_response': [
    'La API devolvió un archivo inválido.',
    'The API returned an invalid file.',
  ],
  'err.upload.generic': ['No se pudo importar el archivo.', 'Could not import the file.'],
  'err.project.project_name_invalid': [
    'El nombre del proyecto no es válido.',
    'The project name is not valid.',
  ],
  'err.project.project_not_found': ['El proyecto ya no existe.', 'The project no longer exists.'],
  'err.project.generic': [
    'No se pudo completar la operación con el proyecto.',
    'Could not complete the project operation.',
  ],
  'err.project.invalid_project': [
    'La API devolvió un proyecto inválido.',
    'The API returned an invalid project.',
  ],
  'err.project.invalid_list': [
    'La API devolvió una lista de proyectos inválida.',
    'The API returned an invalid project list.',
  ],

  // HTTP genérico
  'err.http': ['La API respondió con estado {status}.', 'The API answered with status {status}.'],
  'err.invalid_response': [
    'La API devolvió una respuesta inesperada.',
    'The API returned an unexpected response.',
  ],
  'err.network': ['No se pudo conectar con el servidor.', 'Could not connect to the server.'],

  // Trabajos
  'err.job.project_not_found': ['El proyecto ya no existe.', 'The project no longer exists.'],
  'err.job.media_asset_not_found': [
    'La grabación ya no existe en el proyecto.',
    'The recording no longer exists in the project.',
  ],
  'err.job.option_unknown': [
    'La opción de transcripción elegida no está disponible.',
    'The chosen transcription option is not available.',
  ],
  'err.job.option_not_startable': [
    'Esta opción todavía no se puede iniciar en este equipo.',
    'This option cannot be started on this computer yet.',
  ],
  'err.job.job_already_active': [
    'Ya hay una transcripción en curso para esta grabación.',
    'A transcription is already running for this recording.',
  ],
  'err.job.job_terminal': [
    'La transcripción ya terminó y no se puede cancelar.',
    'The transcription already finished and cannot be cancelled.',
  ],
  'err.job.quality_profile_unknown': [
    'El perfil de calidad elegido no existe.',
    'The chosen quality profile does not exist.',
  ],
  'err.job.transcript_not_found': [
    'La transcripción ya no existe.',
    'The transcript no longer exists.',
  ],
  'err.job.job_prompt_invalid': [
    'Las instrucciones de estilo no son válidas: máximo 600 caracteres.',
    'The style instructions are not valid: 600 characters at most.',
  ],
  'err.job.diarization_models_missing': [
    'Falta el modelo de hablantes. Descárgalo desde la sección Hablantes y vuelve a intentarlo.',
    'The speaker model is missing. Download it from the Speakers section and try again.',
  ],
  'err.job.invalid_response': [
    'La API devolvió una respuesta inesperada.',
    'The API returned an unexpected response.',
  ],
  'err.job.generic': [
    'No se pudo completar la operación (código {code}).',
    'Could not complete the operation (code {code}).',
  ],
  'err.job.create': ['No se pudo crear la transcripción.', 'Could not create the transcription.'],

  'err.profiles.load': [
    'No se pudieron consultar los perfiles de calidad.',
    'Could not load the quality profiles.',
  ],
  'err.profiles.invalid': [
    'La API devolvió perfiles de calidad con un formato inesperado.',
    'The API returned quality profiles in an unexpected format.',
  ],

  'err.options.unavailable': [
    'El servidor no pudo inspeccionar los modelos locales. Vuelve a intentarlo en unos segundos.',
    'The server could not inspect the local models. Try again in a few seconds.',
  ],
  'err.options.http': [
    'No se pudieron consultar las opciones de transcripción (estado {status}).',
    'Could not load the transcription options (status {status}).',
  ],
  'err.options.invalid': [
    'La API devolvió opciones de transcripción con un formato inesperado.',
    'The API returned transcription options in an unexpected format.',
  ],

  'err.glossary.glossary_invalid': [
    'El glosario no es válido: revisa el número de términos y su longitud.',
    'The glossary is not valid: check the number of terms and their length.',
  ],
  'err.glossary.project_not_found': ['El proyecto ya no existe.', 'The project no longer exists.'],
  'err.glossary.generic': [
    'No se pudo completar la operación con el glosario.',
    'Could not complete the glossary operation.',
  ],
  'err.glossary.invalid': [
    'La API devolvió un glosario con un formato inesperado.',
    'The API returned a glossary in an unexpected format.',
  ],

  'err.wave.media_asset_not_found': ['La grabación ya no existe.', 'The recording no longer exists.'],
  'err.wave.peaks_buckets_invalid': [
    'La resolución de la forma de onda no es válida.',
    'The waveform resolution is not valid.',
  ],
  'err.wave.waveform_unavailable': [
    'No se pudo calcular la forma de onda de este audio.',
    'Could not compute the waveform for this audio.',
  ],
  'err.wave.invalid_response': [
    'La API devolvió una forma de onda inválida.',
    'The API returned an invalid waveform.',
  ],
  'err.wave.network_error': [
    'No se pudo conectar con el servidor local.',
    'Could not connect to the local server.',
  ],
  'err.wave.load': ['No se pudo cargar la forma de onda.', 'Could not load the waveform.'],

  'err.speaker.transcript_not_found': ['La transcripción ya no existe.', 'The transcript no longer exists.'],
  'err.speaker.speaker_not_found': ['El hablante ya no existe.', 'The speaker no longer exists.'],
  'err.speaker.speaker_update_invalid': [
    'El nombre debe tener de 1 a 80 caracteres y el color ser #rrggbb.',
    'The name must be 1 to 80 characters and the color must be #rrggbb.',
  ],
  'err.speaker.speaker_merge_invalid': [
    'Solo se pueden fusionar dos hablantes distintos de la misma transcripción.',
    'Only two different speakers of the same transcript can be merged.',
  ],
  'err.speaker.segment_not_found': ['El segmento ya no existe.', 'The segment no longer exists.'],
  'err.speaker.segment_speaker_invalid': [
    'Ese hablante no pertenece a la transcripción del segmento.',
    'That speaker does not belong to the segment transcript.',
  ],
  'err.speaker.network_error': ['No se pudo conectar con el servidor.', 'Could not connect to the server.'],
  'err.speaker.invalid_response': [
    'La API devolvió una respuesta inesperada.',
    'The API returned an unexpected response.',
  ],
  'err.speaker.generic': [
    'No se pudo completar la acción (código {code}).',
    'Could not complete the action (code {code}).',
  ],
  'err.speaker.diarization_models_missing': [
    'Falta el modelo de hablantes. Instálalo en Modelos y vuelve a intentarlo.',
    'The speaker model is missing. Install it in Models and try again.',
  ],
  'err.speaker.job_already_active': [
    'Ya hay un trabajo en curso en este proyecto. Espera a que termine.',
    'A job is already running in this project. Wait for it to finish.',
  ],
  'err.speaker.action': ['No se pudo completar la acción.', 'Could not complete the action.'],
  'err.speaker.reassign': ['No se pudo reasignar el hablante.', 'Could not reassign the speaker.'],

  'err.segment.segment_not_found': ['El segmento ya no existe.', 'The segment no longer exists.'],
  'err.segment.segment_revision_conflict': [
    'El segmento cambió en otro lugar mientras lo editabas.',
    'The segment changed elsewhere while you were editing it.',
  ],
  'err.segment.segment_text_invalid': [
    'El texto del segmento no es válido.',
    'The segment text is not valid.',
  ],
  'err.segment.network_error': ['No se pudo conectar con el servidor.', 'Could not connect to the server.'],
  'err.segment.invalid_response': [
    'La API devolvió una respuesta inesperada.',
    'The API returned an unexpected response.',
  ],
  'err.segment.generic': [
    'No se pudo guardar el segmento (código {code}).',
    'Could not save the segment (code {code}).',
  ],
  'err.segment.save': ['No se pudo guardar el segmento.', 'Could not save the segment.'],

  'err.model.disk_space_insufficient': [
    'No hay espacio libre suficiente en el disco. Libera espacio y vuelve a intentarlo.',
    'There is not enough free disk space. Free up some space and try again.',
  ],
  'err.model.model_installation_network_error': [
    'No se pudo conectar para descargar el modelo. Revisa tu conexión a Internet y reintenta.',
    'Could not connect to download the model. Check your Internet connection and retry.',
  ],
  'err.model.model_installation_http_error': [
    'El servidor de descarga respondió con un error. Inténtalo de nuevo más tarde.',
    'The download server answered with an error. Try again later.',
  ],
  'err.model.model_installation_download_failed': [
    'La descarga del modelo falló. Inténtalo de nuevo.',
    'The model download failed. Try again.',
  ],
  'err.model.model_installation_io_error': [
    'No se pudo escribir el modelo en el disco. Revisa los permisos y el espacio.',
    'Could not write the model to disk. Check permissions and space.',
  ],
  'err.model.model_installation_invalid_snapshot': [
    'Los archivos recibidos no corresponden al modelo esperado. Reintenta la instalación.',
    'The received files do not match the expected model. Retry the installation.',
  ],
  'err.model.model_installation_cancelled': ['La instalación fue cancelada.', 'The installation was cancelled.'],
  'err.model.model_install_unconfirmed': [
    'Falta confirmar la instalación del modelo.',
    'The model installation still needs to be confirmed.',
  ],
  'err.model.model_unknown': ['Ese modelo no está en el catálogo.', 'That model is not in the catalog.'],
  'err.model.model_already_installed': ['Ese modelo ya está instalado.', 'That model is already installed.'],
  'err.model.external_model_not_found': [
    'La copia local de este modelo ya no está disponible. Descárgalo desde HuggingFace.',
    'The local copy of this model is no longer available. Download it from HuggingFace.',
  ],
  'err.model.model_task_terminal': ['La tarea ya había terminado.', 'The task had already finished.'],
  'err.model.model_task_not_found': ['La tarea ya no existe.', 'The task no longer exists.'],
  'err.model.model_delete_unconfirmed': [
    'Falta confirmar el borrado del modelo.',
    'The model deletion still needs to be confirmed.',
  ],
  'err.model.model_not_installed': ['Ese modelo no está instalado.', 'That model is not installed.'],
  'err.model.model_in_use': [
    'El modelo está en uso por una transcripción en curso. Espera a que termine o cancélala y vuelve a intentarlo.',
    'The model is in use by a running transcription. Wait for it to finish or cancel it, then try again.',
  ],
  'err.model.model_remove_failed': [
    'No se pudo borrar el modelo por un error de disco.',
    'Could not delete the model because of a disk error.',
  ],
  'err.model.model_task_failed': ['La tarea de instalación falló.', 'The installation task failed.'],
  'err.model.invalid_response': [
    'La API devolvió una respuesta con formato inesperado.',
    'The API returned a response in an unexpected format.',
  ],
  'err.model.network_error': ['No se pudo conectar con el servidor.', 'Could not connect to the server.'],
  'err.model.checksum': [
    'Un archivo descargado no coincide con su suma de verificación (checksum). Se descartó; reintenta la descarga.',
    'A downloaded file does not match its checksum. It was discarded; retry the download.',
  ],
  'err.model.generic': [
    'No se pudo completar la operación (código {code}).',
    'Could not complete the operation (code {code}).',
  ],
  'err.model.tasks': [
    'No se pudo consultar el estado de las tareas.',
    'Could not check the state of the tasks.',
  ],
  'err.model.op': [
    'No se pudo completar la operación. Inténtalo de nuevo.',
    'Could not complete the operation. Try again.',
  ],

  'err.provider.provider_not_found': ['Ese proveedor no existe.', 'That provider does not exist.'],
  'err.provider.secrets_key_invalid': [
    'La clave no es válida: usa de 1 a 512 caracteres ASCII visibles, sin espacios.',
    'The key is not valid: use 1 to 512 visible ASCII characters, with no spaces.',
  ],
  'err.provider.secrets_file_insecure': [
    'El archivo de secretos de V no es seguro (debe ser un archivo normal con permisos 0600). Corrige sus permisos y reintenta.',
    'The V secrets file is not safe (it must be a regular file with 0600 permissions). Fix its permissions and retry.',
  ],
  'err.provider.secrets_file_invalid': [
    'No se pudo leer el archivo de secretos de V. Revísalo o bórralo y reintenta.',
    'Could not read the V secrets file. Check it or delete it and retry.',
  ],
  'err.provider.secrets_write_failed': [
    'No se pudo guardar la clave en el disco. Revisa los permisos y el espacio.',
    'Could not save the key to disk. Check permissions and space.',
  ],
  'err.provider.media_not_found': ['La grabación ya no existe.', 'The recording no longer exists.'],
  'err.provider.media_duration_unknown': [
    'No se conoce la duración de la grabación.',
    'The duration of the recording is not known.',
  ],
  'err.provider.invalid_response': [
    'La API devolvió una respuesta con formato inesperado.',
    'The API returned a response in an unexpected format.',
  ],
  'err.provider.generic': [
    'No se pudo completar la operación (código {code}).',
    'Could not complete the operation (code {code}).',
  ],
  'err.provider.op': [
    'No se pudo completar la operación. Inténtalo de nuevo.',
    'Could not complete the operation. Try again.',
  ],
} as const satisfies Catalog
