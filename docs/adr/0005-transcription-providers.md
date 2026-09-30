# ADR-0005: Port de providers de transcripción sin framework de plugins

- Estado: Aceptada
- Fecha: 2026-09-30
- Responsables: mantenedores de VOZ
- Alcance: contrato `TranscriptionProvider`, registry y regla de crecimiento de
  providers (S16.15)
- Relacionadas: [ADR-0001](0001-modular-monolith.md) (fronteras),
  [ADR-0004](0004-local-asr-and-recoverable-chunks.md) (Faster Whisper),
  [ADR-0006](0006-local-first-privacy.md) (cloud solo por elección explícita)
- Diagramas: [componentes](../architecture/03-componentes.md)

## Contexto

El plan maestro prevé varios motores: Faster Whisper (local principal),
whisper.cpp, OpenAI y ElevenLabs (cloud opcionales), además de diarización y
alignment. Los casos de uso no deben conocer tipos de un SDK concreto. Al mismo
tiempo, [AGENTS.md](../../AGENTS.md) prohíbe construir un framework de plugins
dinámico antes de que al menos dos providers reales demuestren la abstracción
necesaria.

Hoy existe **un único provider real**: Faster Whisper. Diseñar el punto de
extensión a partir de un solo ejemplo tiende a fijar detalles de ese motor en el
contrato, así que la abstracción se mantiene mínima y se revisa cuando llegue el
segundo.

## Decisión

1. **Port único y estructural.** `TranscriptionProvider` es un `Protocol`
   `runtime_checkable` en `src/voz/application/ports/transcription.py`, con la
   propiedad `provider_id` y el método
   `transcribe(*, audio: BinaryIO, options: TranscriptionOptions, cancellation: TranscriptionCancellationToken | None) -> TranscriptionResult`.
   Los adapters no heredan de application: cumplen el protocolo.
2. **Tipos canónicos independientes del motor** en el mismo módulo:
   `TranscriptionOptions` (`ModelDescriptor`, idioma opcional y `TranscriptionClip`
   opcional), `TranscriptionResult` y `TranscriptionSegment` (milisegundos
   enteros, ordenados y sin solapes, texto literal), `TranscriptionFailureCode`
   (`transcription_model_not_installed`, `transcription_gpu_unavailable`,
   `transcription_invalid_audio`, `transcription_provider_failed`,
   `transcription_cancelled`) y `TranscriptionError` con mensaje seguro y
   `retryable`. Los tipos del SDK (engine, segmentos, `compute_type`) permanecen
   privados en el adapter (`_Engine`, `_EngineSegment` en
   `src/voz/infrastructure/asr/faster_whisper.py`).
3. **Identidad del modelo en el dominio.** `ModelDescriptor` y
   `ProcessingProfile` (`src/voz/domain/entities/`) llevan `provider_id`,
   modelo, procedencia (`source` + `revision` fija) y capacidades
   (`ModelCapability`). El audio llega como descriptor abierto, nunca como ruta.
4. **Registry explícito y determinista.**
   `TranscriptionProviderRegistry`
   (`src/voz/application/transcription_provider_registry.py`) es un diccionario
   en memoria inyectado por constructor: valida que el candidato implemente el
   port, que `provider_id` sea un identificador seguro (`[a-z0-9][a-z0-9._-]{0,63}`),
   rechaza duplicados sin reemplazar y lista en orden léxico. No descubre
   módulos, no importa por nombre y no lee configuración.
5. **Composición en un solo lugar.** `create_local_asr_runtime`
   (`src/voz/bootstrap.py`) construye `FasterWhisperProvider` para un descriptor
   exacto y lo registra; `create_app` expone `provider_for(selection)` al
   `JobRunner`, que recibe un `Callable[[JobSelection], TranscriptionProvider]`
   y nunca importa un adapter.
6. **Regla de no plugin framework.** Hasta que existan **dos providers reales
   ejecutados** (no dobles de prueba), no se añaden entry points, carga dinámica
   de módulos, manifests de plugin, jerarquías base ni generalización de
   `create_local_asr_runtime`. El registry actual es un mapa, no un mecanismo de
   plugins. La aparición del segundo provider (whisper.cpp, Sección 9, o un
   cloud opcional) obliga a revisar esta ADR y a extraer solo lo que los dos
   compartan de verdad.
7. **Capacidades adicionales, contratos separados y posteriores.**
   `DiarizationProvider` y `AlignmentProvider` (mencionados en ADR-0001) no
   existen; se crearán con su sección del roadmap y sus propios tipos
   canónicos, no como métodos opcionales de `TranscriptionProvider`.
8. **Providers cloud** implementarán el mismo port, pero solo se seleccionan
   por decisión explícita del usuario y siguen las reglas de
   [ADR-0006](0006-local-first-privacy.md). No existen en el código.

## Consecuencias positivas

- Los casos de uso (`RecoverableTranscription`, `JobRunner`) se prueban con
  providers falsos y no importan ningún SDK.
- Cambiar de motor no altera la representación canónica del transcript ni la
  UI.
- La ausencia de un framework de plugins evita compromisos de API pública con
  un solo ejemplo.
- Los errores llegan a la API como códigos estables sin rutas ni tracebacks.

## Costes y límites

- Con un solo provider, el registry aporta poco más que validación de
  identidad; se conserva porque ya es la superficie que el segundo provider
  usará.
- Partes del sistema son hoy específicas de Faster Whisper por diseño:
  `create_local_asr_runtime` rechaza descriptores de otro provider con
  `ValueError`; `provider_for` en `create_app` siempre construye un runtime local
  de Faster Whisper; `LocalTranscriptionModelCatalog` y
  `FasterWhisperRuntimeProbe` (`src/voz/infrastructure/asr/options.py`) solo
  conocen ese motor. Añadir otro exigirá generalizar esos puntos (y solo
  entonces).
- El port no incluye `close()`: la liberación de recursos pertenece al dueño
  del adapter en el composition root ([ADR-0004](0004-local-asr-and-recoverable-chunks.md)).
- La suite contractual ejecuta un provider estructural y `FasterWhisperProvider`
  con un engine falso; el camino con modelo real es un smoke opt-in. La prueba
  de que el contrato es suficiente llegará con el segundo motor real.
- Word timestamps, traducción y diarización no forman parte del contrato actual.

## Alternativas consideradas

### Framework de plugins (entry points, carga dinámica, manifests)

Rechazada por ahora. Prohibido por AGENTS.md hasta tener dos providers reales;
añadiría superficie de seguridad y compatibilidad sin un segundo caso de uso.

### Clase base abstracta (`ABC`) en lugar de `Protocol`

Rechazada. Obligaría a los adapters a importar application y a heredar; el
protocolo estructural mantiene la dependencia hacia adentro y permite dobles
simples en tests.

### Un solo port «ASR» con transcripción, alineación y diarización

Rechazada. Las capacidades varían por motor y evolucionan por separado; se
modelan como puertos independientes cuando existan.

### Selección de provider mediante condicionales en los casos de uso

Rechazada. Filtra detalles de motores a application y obliga a modificarla por
cada proveedor nuevo.

### Registro global (singleton) o service locator

Rechazada. Oculta dependencias y dificulta los tests; el registry es una
instancia inyectada desde el composition root.

## Evidencia actual (2026-09-30)

| Requisito | Código o prueba |
| --- | --- |
| Port y tipos canónicos | `src/voz/application/ports/transcription.py`, `tests/contract/test_transcription_provider.py` (validación de segmentos, resultado y opciones) |
| Contrato compartido por implementaciones | mismo archivo, fixture `provider_case` con `structural` y `faster-whisper`: audio válido, timestamps monótonos, audio inválido tipado, cancelación |
| Registry: identidad, duplicados, orden, snapshot inmutable, rechazo de no-providers | `tests/unit/application/test_transcription_provider_registry.py` |
| Registry sin imports de infraestructura o frameworks | `test_registry_has_no_domain_infrastructure_or_framework_imports` |
| Faster Whisper único adapter real | `src/voz/infrastructure/asr/faster_whisper.py` (`provider_id = "faster-whisper"`) y `tests/unit/infrastructure/asr/` |
| Composición explícita sin descargas | `tests/unit/test_asr_bootstrap.py` (`providers.provider_ids() == ("faster-whisper",)`, rechazo de otro provider) |
| El job usa el provider vía factoría | `tests/integration/application/test_job_runner.py` |

## Verificación

Esta decisión se considera respetada cuando:

- ningún caso de uso importa un módulo bajo `voz.infrastructure`;
- todo provider expone un `provider_id` seguro, único en el registry;
- todo provider nuevo se añade a la suite `tests/contract/` y pasa los mismos
  casos;
- los tipos del SDK no aparecen en firmas públicas de application ni en la API;
- no existe código de descubrimiento dinámico de providers mientras solo haya
  uno real.

**Criterio de revisión:** al integrar el segundo provider real, actualizar o
sustituir esta ADR con lo que ambos comparten y retirar los puntos específicos
de Faster Whisper enumerados en «Costes y límites».
