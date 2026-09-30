# ADR-0007: Diarización local con sherpa-onnx (sin torch ni token)

- Estado: Aceptada
- Fecha: 2026-09-30
- Responsables: mantenedores de VOZ
- Alcance: motor por defecto de diarización y su instalación de modelos
  (S6.04, S6.05-S6.07, S6.16)
- Relacionadas: [ADR-0005](0005-transcription-providers.md) (providers),
  [ADR-0006](0006-local-first-privacy.md) (local-first, descargas explícitas)

## Contexto

La diarización responde «quién habló cuándo» y alimenta speakers editables. El
candidato habitual, pyannote `speaker-diarization-community-1`, exige PyTorch
(cientos de MB de dependencias) y un token de Hugging Face con aceptación de
términos. Eso contradice el objetivo de VOZ: local, gratis, open source y sin
cuentas (ADR-0006). Tampoco conviene que la instalación por defecto arrastre
torch junto a CTranslate2 en un sistema inmutable (Bazzite).

## Decisión

1. **Motor:** `sherpa-onnx` (ONNX Runtime, wheels CPU, sin torch) detrás del port
   `DiarizationProvider` (`src/voz/application/ports/diarization.py`). Es un
   extra opcional (`pip install voz[diarization]`); se importa de forma
   perezosa y, si falta, el error es `diarization_runtime_unavailable`.
2. **Modelos fijados** (sin token; URL, tamaño y SHA-256 verificados antes de
   publicar):
   - segmentación: `sherpa-onnx-pyannote-segmentation-3-0` (export ONNX de
     pyannote/segmentation-3.0), licencia **MIT**;
   - embeddings: `wespeaker_en_voxceleb_resnet34_LM.onnx` (WeSpeaker ResNet34),
     licencia **Apache-2.0**.
   Se instalan solo por acción explícita (`DiarizationModelStore.install`) en
   `<XDG data>/models/diarization/`, con `.part`, reanudación por `Range`,
   publicación atómica y un manifiesto; nunca se descargan al importar ni al
   diarizar.
3. **Clustering:** `FastClustering` de sherpa. Automático por umbral (0.3);
   exacto con `num_clusters=N`; rango mín/máx = automático y, si el resultado
   queda fuera, una segunda pasada con `num_clusters` recortado al límite, sin
   recargar los modelos (`set_config` solo cambia el clustering).
4. **Umbral 0.3.** Medido con diálogo sintético en español: 0.5 fusiona voces
   distintas y 0.3 separa A/B/A. Se prefiere sobre-segmentar: fusionar speakers
   en la UI es trivial; separar una voz fusionada no lo es.
5. **Contrato:** entrada WAV PCM s16 mono 16 kHz (el derivado normalizado del ASR;
   otro formato es `diarization_invalid_audio`); salida `DiarizedTurn` en ms
   enteros ordenados con `cluster` opaco. La cancelación se sondea desde el
   callback de progreso nativo. Las rutas del host no salen de la infraestructura.

## Consecuencias positivas

- Instalación ligera (~33 MB de modelos) y sin cuentas; funciona sin red tras la
  descarga explícita.
- Corre en CPU; no compite por VRAM con el ASR (S14.07).
- El port permite sustituir el motor sin tocar casos de uso.

## Costes y límites

- Calidad algo inferior a pyannote Community-1; el embedding es entrenado en
  VoxCeleb (inglés), la separación en español se apoya en voz, no en idioma.
- El clustering rápido no modela solapamiento de voces más allá de lo que da la
  segmentación; la reconciliación con segmentos de ASR vive en application.
- Rango = como mucho dos pasadas (segmentación + embeddings se repiten;
  ponytail: solo el clustering podría cachearse con un cambio upstream).
- El audio se carga entero en memoria como float32 (unos 230 MB por hora).

## Alternativas consideradas

| Alternativa | Por qué no es la opción por defecto |
| --- | --- |
| pyannote Community-1 con torch | Requiere torch y token HF con términos aceptados |
| NVIDIA NeMo (MSDD/Sortformer) | Dependencias muy pesadas; orientado a GPU/CUDA |
| WhisperX | Acopla ASR, alineación y diarización (que usa pyannote y token) |

## Cómo cambiar de modelo

Cambiar el catálogo fijado en `DiarizationModelStore` (URL, tamaño, SHA-256 y
nombres de archivo) y las rutas pasadas a `SherpaOnnxDiarizationProvider`;
otro motor completo solo necesita implementar `DiarizationProvider`. El
manifiesto compara las fuentes fijadas, así que un catálogo distinto fuerza una
reinstalación limpia.

## Evidencia actual (2026-09-30)

| Requisito | Código o prueba |
| --- | --- |
| Descarga verificada, reanudable y atómica | `src/voz/infrastructure/diarization/models.py`, `tests/unit/infrastructure/diarization/test_diarization_models.py` |
| Provider, WAV estricto, cancelación, errores tipados | `src/voz/infrastructure/diarization/sherpa.py`, `tests/unit/infrastructure/diarization/test_sherpa_provider.py` |
| Auto / rango / exacto con motor falso | mismo archivo (`test_range_reruns_clamped_without_reloading_models`) |
| Prueba real opt-in | `test_real_engine_finds_at_least_two_speakers` (`VOZ_DIARIZATION_E2E_MODELS` y `VOZ_DIARIZATION_E2E_AUDIO`) |

## Verificación

Esta decisión se considera respetada cuando:

- ningún módulo fuera de `infrastructure/diarization` importa `sherpa_onnx`;
- ninguna ruta descarga modelos sin una llamada explícita a `install`;
- el extra `diarization` no añade torch al entorno;
- todo modelo nuevo se fija con tamaño y SHA-256.
