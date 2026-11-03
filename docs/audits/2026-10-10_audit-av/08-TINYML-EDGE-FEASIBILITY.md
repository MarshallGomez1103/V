# 08 · Viabilidad TinyML y edge

## Principio

No hay evidencia en el repositorio de ejecución en ningún dispositivo embebido. Las cifras de esta sección son de fuentes públicas, marcadas como tales, o son hipótesis que hay que medir. **No se promete compatibilidad con ESP32, relojes ni microcontroladores.**

## Clases de hardware

| Clase | Ejemplo | RAM típica | Sistema | Encaje con VOZ |
|---|---|---|---|---|
| 1. CPU limitada en PC | Portátil sin GPU | 8–16 GB | Sistema completo | Ya cubierto (CPU con `small`/`base`) |
| 2. SBC Linux ARM | Raspberry Pi 5, Rockchip RK3588 | 4–8 GB | Linux completo | Viable para STT; hay que medir |
| 3. Microcontrolador | ESP32-S3 (con PSRAM) | Decenas-cientos de KB + PSRAM | Sin SO completo (RTOS) | Solo wake-word y comandos fijos |
| 4. Wearable con SO | Reloj con Wear OS o similar | 1–2 GB, batería | SO móvil | Solo TTS de frases o comandos; no STT completo |
| 5. Sin SO completo | MCU sin FS ni malloc completo | Muy limitada | Bare-metal o RTOS | Reproducción de frases pregrabadas |

## Tecnologías y su encaje

| Tecnología | Función | Fuente verificada | Limitación |
|---|---|---|---|
| whisper.cpp (MIT) | STT completo en CPU/ARM | README oficial: soporta Raspberry Pi; cuantización enteras de modelos ggml (Q5_0 citado); backends CUDA, Vulkan, Metal, CoreML, etc. | Memoria: tiny ~273 MB, base ~388 MB, small ~852 MB (tabla del README). Disco: tiny 75 MiB, base 142 MiB |
| ONNX Runtime / ONNX Runtime Mobile | Inferencia genérica | Ya usado por sherpa-onnx en VOZ | Mobile: no evaluado en esta auditoría |
| TFLite Micro | Inferencia en MCU | Referencia general | No verificado en esta auditoría |
| microWakeWord (ESPHome) | Wake-word on-device | Página ESPHome y Home Assistant: detección en ESP32-S3 con PSRAM; open source | **Licencia y tamaño de modelo no encontrados** en fuentes consultadas |
| KittenTTS nano/micro/mini 0.8 (ONNX) | TTS en CPU | Model cards HF y README: nano int8 ~25 MB, micro 41 MB, mini 80 MB; 24 kHz | Sin cifras de CPU ni RAM en fuentes primarias |
| KittenTTS 2 | TTS completo | Requiere PyTorch (HF); README: GPU ~8 GB o CPU ~6 GB RAM | **Fuera de edge** |
| Modelos Whisper tiny/base en ARM | STT en SBC | Fuente secundaria (Turing Pi): tiny ~175 MB, base ~280 MB de RAM | No verificado; la fuente oficial da cifras distintas (ver arriba) |

Estimación del README de whisper.cpp citada tal cual; las de Turing Pi son orientativas. Se dan ambas porque no coinciden.

## Clasificación por capacidad

| Capacidad | Clase 1 | Clase 2 (SBC) | Clase 3 (MCU) | Clase 4 (wearable SO) | Clase 5 |
|---|---|---|---|---|---|
| STT completo (archivos largos) | Sí (ya) | Posible con tiny/base; **a medir** | No | No | No |
| Reconocimiento de comandos cortos | Sí | Sí | Posible con modelos de keywords | Posible | Posible con lista fija |
| Wake-word | Sí | Sí | Sí (microWakeWord, ESP32-S3 según fuente) | Sí si el SO lo permite | Depende |
| TTS completo (KittenTTS 2) | Sí, con GPU o CPU fuerte | No | No | No | No |
| TTS ligero (KittenTTS 0.8 ONNX) | Sí | Posible; a medir | Improbable | Posible; a medir | No |
| Reproducción de frases pregrabadas | Sí | Sí | Sí | Sí | Sí |

## Propuesta de benchmarks

Ejecutar solo con autorización y en el hardware objetivo. Mismo protocolo para todas las clases.

| Métrica | Cómo | Dónde |
|---|---|---|
| Latencia de primer resultado | Tiempo desde la entrada hasta el primer segmento o primer audio | Todas |
| Realtime factor (RTF) | Cómputo / duración de audio; < 1 es más rápido que tiempo real | Clases 1–4 |
| RAM pico | `ru_maxrss` del proceso y, si existe, de los hilos | Clases 1–4 |
| CPU | Muestreo de uso medio y pico durante la inferencia | Clases 1–4 |
| Tamaño del modelo | Bytes en disco del artefacto cuantizado | Todas |
| Tiempo de carga | Desde arranque hasta primera inferencia | Todas |
| Energía | Medida con instrumentación externa cuando exista | Solo si hay instrumento |
| Calidad | WER/CER con el mismo corpus (`voz bench`) | Clases 1–2 |

Reutilizar `voz bench` (ya mide RTF, pico RSS, VRAM y WER/CER) para clases 1 y 2. Para 3–5 hace falta un harness propio.

## Riesgos y lo que no se sabe

- Ningún dispositivo de la lista está probado con VOZ.
- Licencia y tamaño de microWakeWord: no encontrados.
- Cifras de RAM de whisper.cpp en Raspberry Pi: fuentes contradictorias y ninguna medida en Pi. Un blog de 2026 da "tiny comfortably faster than real time on Pi 5" sin cifras; se trata como no verificado.
- Un modelo ONNX de 25 MB no implica que quepa ni funcione en un MCU: hay que medir la RAM de activación, no solo el archivo.
- Hardware real siempre difiere del papel: el calibrado de reloj, sensores y audio requiere tuning en el dispositivo.

## Recomendación

1. Priorizar clase 2 (SBC) con whisper.cpp tiny/base cuantizado, después de medir en un Pi real. Sin medición, no se afirma nada.
2. Clase 3: solo wake-word y comandos, con microWakeWord, después de confirmar su licencia y tamaño. Fuera de alcance del producto principal.
3. Clase 4 y 5: solo reproducción de frases pregrabadas, sin modelo.
4. No mezclar edge con el núcleo de VOZ en el mismo corte: es un proyecto de investigación separado.
