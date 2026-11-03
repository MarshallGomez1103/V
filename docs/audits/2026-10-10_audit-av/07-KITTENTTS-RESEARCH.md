# 07 · Estudio técnico de KittenTTS

Fecha de consulta: 2026-10-10. Todas las cifras proceden de fuentes web consultadas en esta sesión; cuando una fuente no da un dato, se dice. Ninguna cifra es medida por VOZ.

## Fuentes consultadas

| Fuente | URL | Qué aporta |
|---|---|---|
| README oficial | https://raw.githubusercontent.com/KittenML/KittenTTS/main/README.md | Familias, tamaños, runtimes, voces, API, licencias |
| Repositorio oficial | https://github.com/KittenML/KittenTTS | Licencia del código, paquete PyPI, actividad |
| Model card KittenTTS 2 | https://huggingface.co/KittenML/kitten-tts-2 | Licencia de pesos, framework, tamaños de archivo |
| Model card 0.8 int8 | https://huggingface.co/KittenML/kitten-tts-nano-0.8-int8 | Metadatos de licencia y de instalación 0.8 |
| Búsqueda de versiones | Resultados web sobre KittenTTS nano/micro/mini | Fechas (con conflicto entre fuentes) |
| Análisis de licencia (secundario) | https://www.stork.ai/blog/kittentts-2-got-biggerand-more-complicated | Interpretación de la licencia; no es fuente primaria |
| Referencia de app: vibe | https://github.com/thewh1teagle/vibe (README y LICENSE) | Licencia MIT; Tauri; whisper.cpp; diarización; gestión de modelos |

Limitación: no se pudo leer el texto completo de la licencia de Stellon Labs (el enlace no estaba en la respuesta del modelo). Los detalles de redistribución quedan como **no verificados**.

## Distinción obligatoria: KittenTTS 0.8 y KittenTTS 2

| Aspecto | KittenTTS 0.8 (familia "legacy" ONNX) | KittenTTS 2 |
|---|---|---|
| Naming en HF | `KittenML/kitten-tts-{nano,micro,mini}-0.8*` | `KittenML/kitten-tts-2` |
| Arquitectura | ONNX; StyleTTS2-based según el port comunitario (fuente secundaria) | "1,7 B parámetros, 1-bit speech language model" (README) |
| Runtime | ONNX Runtime (instalado con el paquete base según README) | PyTorch según model card de HF; GGUF para `kitten-tts-2-cpp` (llama.cpp fork); vLLM opcional con CUDA |
| Paquete Python | Wheel `kittentts-0.8.0-py3-none-any.whl` desde la **release de GitHub** (HF lo indica así) | `pip install kittenml` (PyPI); versión no indicada en README |
| Tamaños | nano int8 ~25 MB; nano fp32 56 MB; micro 41 MB; mini 80 MB (README) | 947 MiB por defecto (lossless); 506 MiB con `emb4` (README); HF lista `packed` 954 MB y `emb4` 469 MB |
| Requisito de dispositivo | CPU | GPU CUDA con ~8 GB libres **o** CPU con ~6 GB RAM (README) |
| Python | Requiere 3.9+ (README) para el paquete; el wheel 0.8 no declara versión en HF | Python 3.10+ (HF) |
| Voces | 8 de 0.8 (Bella, Jasper, Luna, Bruno, Rosie, Hugo, Kiki, Leo) según README | 47 voces integradas, incluidas las 8 anteriores (README) |

Discrepancias de fuentes que hay que resolver antes de decidir:

1. **Framework de KittenTTS 2**: el README dice que "el framework subyacente del camino por defecto no se indica"; la model card de HF dice que el modelo "requires Python 3.10 or later and PyTorch". Tomar la model card como verdad hasta confirmarlo.
2. **Tamaño de KittenTTS 2**: el README lista 506 MiB; la model card lista 954 MB `packed` (default) y 469 MB `emb4`. Son unidades distintas (MiB frente a MB) y variantes distintas. No es contradicción grave, pero hay que citar la variante.
3. **Fecha de la familia 0.8**: las búsquedas dan fechas distintas (febrero de 2026 y mayo de 2026 según fuentes secundarias). No verificado con la release oficial.

## Licencias

| Componente | Licencia | Fuente | Implicación |
|---|---|---|---|
| Código `KittenML/KittenTTS` | Apache-2.0 | README y badge | Permisiva; exige conservar avisos (NOTICE) |
| Paquete `kittenml` | Apache-2.0 | Model card KittenTTS 2 | Igual |
| Pesos KittenTTS 2 | **Stellon Labs Community License** | Model card HF (cita textual: "These weights are released under the Stellon Labs Community License.") | **Condiciona la integración** (ver abajo) |
| Modelo de speaker-embedding (`speaker/`) | MIT | Model card HF | Permisiva |
| Pesos 0.8 int8 | Metadato HF: `apache-2.0` | HF metadata (campo `License: apache-2.0`) | El README de GitHub no declara licencia de pesos. Verificar en la release |
| Port JavaScript `kitten-tts-js` | No afiliado; comunitario | Búsqueda | No usar como fuente de licencia |

Términos clave de la licencia de Stellon Labs, según la model card (cita) y el análisis secundario:

- "Research, non-commercial and limited commercial use are free of charge."
- Cap: "the commercial grant ends once you or your affiliates pass USD $1,000,000 in annual revenue or in total cumulative funding." Por encima, "you need a separate license from Stellon Labs."
- "Distributing the weights, a derivative, or a product built on them carries attribution requirements." Remite a una "Section IV(a)" que no se pudo leer.
- Secundario (no verificado en texto primario): registro comercial, atribución "Powered by Stellon Labs", concesión revocable, política de uso aceptable no pública.

**Conclusión para VOZ**: los pesos KittenTTS 2 **no pueden incluirse en un instalador ni en un release público** sin una revisión legal del texto completo y, si el propietario quiere uso comercial, un contrato o licencia separada con Stellon Labs. Para investigación y uso personal local, la licencia permite el uso. Esto es una decisión del propietario, no técnica.

Referencia de app: `thewh1teagle/vibe` es **MIT** (LICENSE verificado). Su stack es Tauri y soporta whisper.cpp, Parakeet TDT v3 y Nemotron 3.5. Se puede estudiar y adaptar con atribución (AGENTS.md, regla 10).

## Capacidades

| Capacidad | KittenTTS 0.8 | KittenTTS 2 |
|---|---|---|
| Idiomas | Inglés (no detallado por fuente) | 20 listados, incluidos inglés, chino, hindi, japonés, suajili |
| Salida | 24 kHz | 24 kHz |
| Streaming | No documentado para 0.8 | `generate_stream` por **chunk** (no por token); texto < ~380 caracteres = un solo chunk; los chunks no tienen el post-procesado de costuras de `generate` |
| Lotes | No indicado | No indicado |
| Clonación de voz | No | Sí: referencia de 5–30 s; si no hay transcripción, usa Whisper para generarla |
| Controles de expresión | No | Beta: etiquetas `[emotion]`, eventos `<event>`, énfasis `(((x)))`, `preset` |
| API pública | `KittenTTS(...)` (según model card 0.8, con `soundfile` para guardar) | `from kittenml import KittenTTS`; `generate`, `generate_to_file`, `generate_stream`; `sample_rate`, `available_voices`; `weights="emb4"`, `preset`, `reference`, `reference_text`, `backend="vllm"` |

Rendimiento: el README da cifras solo en **A100**: 936 caracteres, primeros 21 s de audio en 17 s; 54 s de audio en 42 s. **No hay cifras de CPU.** Ninguna cifra es de VOZ.

Calidad de clonación: el README reporta similitud de locutor 0,49–0,72 con su propia referencia y 0,01–0,18 con las otras 37 voces integradas. Es una cifra del autor; no verificada.

## Mantenimiento

Según la página del repositorio consultada: 15,8 k estrellas, 909 forks, 86 issues abiertas, 41 PRs abiertos, **48 commits** en total, sin releases ni tags visibles, y sin fechas de último commit en la vista. La página ofrece soporte comercial y una API alojada gratuita, pero no afirma estado de mantenimiento. **Riesgo de estabilidad de API**: sin releases, la versión a fijar debe ser un commit o un hash de wheel, no un tag.

## Dependencias y compatibilidad con VOZ

- VOZ requiere Python 3.12 y **no usa torch** (ADR-0007 lo evitó explícitamente, con sherpa-onnx). KittenTTS 2 exige PyTorch según HF. Meterlo en el entorno principal rompería esa decisión y añadiría gigabytes. **Debe aislarse.**
- KittenTTS 0.8 usa ONNX Runtime (README). Si la versión que requiere choca con la de sherpa-onnx en el mismo entorno es algo que no se verificó; por eso debe ir en un entorno separado.
- `soundfile` es necesario para guardar WAV en el ejemplo oficial (model card 0.8).
- No se encontró requisito de espeak/phonemizer en las fuentes consultadas; no verificado en el código fuente del paquete.

## Opciones de integración (análisis, no implementación)

| Opción | Memoria | Dependencias | Estabilidad | Packaging | Veredicto |
|---|---|---|---|---|---|
| A. Cargar dentro del proceso del servidor | Alta: cada modelo queda residente en el mismo intérprete | Contamina el entorno principal; KittenTTS 2 trae torch | Un fallo nativo tumba el servidor. La llamada nativa retiene el GIL (ver `worker.py` del repo) | Simple | **Descartar** |
| B. Worker aislado en hilo | Igual que A | Igual que A | El GIL bloquea la UI igual que en diarización | Simple | **Descartar** para modelos ONNX/torch largos |
| C. Subproceso con protocolo por pipes (como diarización) | Solo mientras dura la síntesis | Entorno propio para el subproceso | Un crash no tumba el servidor; cancelable matando el proceso | Medio | **Recomendada** para KittenTTS 2 |
| D. Entorno Python separado (uv project propio) + subproceso | Igual que C | Totalmente aislado; permite torch sin tocar VOZ | Igual que C | Requiere instalar y mantener un segundo entorno | **Recomendada junto con C** para KittenTTS 2 |

Recomendación: **D + C** para KittenTTS 2 (torch y pesos aparte, comunicación por stdin/stdout), y **C** para 0.8 (ONNX) para mantener un único patrón. Ambos siguen el precedente verificado de diarización (`infrastructure/diarization/worker.py`), que ya demuestra el patrón en el repo.

## Adapter conceptual: `SpeechSynthesisProvider` (sin implementar)

Concepto para el arquitecto, siguiendo AGENTS.md:

- Puerto en `application/ports/speech_synthesis.py`: `synthesize(text, voice, language, options, cancellation) -> AudioResult`, con `available_voices()` y `describe()`.
- Entidades de dominio nuevas: `SpeechSynthesisJob` o reutilizar `TranscriptionJob` con un tipo, y `SynthesizedAudio` (ruta relativa, duración, sample rate, hash).
- Adaptador `infrastructure/tts/kittentts_worker.py` que habla con el subproceso; nunca importa `kittenml` en el proceso principal.
- Registro de proveedores igual al de ASR (`transcription_provider_registry.py`), con rechazo de duplicados.
- Consentimiento para clonación: obligatorio y explícito (ver `12`), y referencias de voz nunca enviadas a ningún servicio.

## Riesgos

1. Licencia de pesos KittenTTS 2 (ver arriba): **bloqueo de distribución**.
2. Sin releases: fijar commit y hash de wheel.
3. Dependencia de torch (KittenTTS 2): aislar.
4. Clonación de voz: riesgo de suplantación; exige consentimiento y marca de audio generado.
5. Calidad y rendimiento en CPU: no medidos en fuentes públicas; requiere benchmark propio en hardware objetivo (sin ejecutar en esta auditoría).
