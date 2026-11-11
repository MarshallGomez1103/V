# 12 · Roadmap preliminar propuesto

Propuesta, no sustituye a `ROADMAP.md`, que no se modificó. Cada corte debe ser pequeño, con IDs nuevos que no renumeran los existentes (regla de `ROADMAP.md`). Los IDs `AV-*` se refieren a `11-TECHNICAL-DEBT.md`. Las estimaciones de esfuerzo no se incluyen porque no hay base medida.

Orden: estabilización primero, luego rename, luego TTS. Ninguna fase de TTS empieza sin cerrar las decisiones de `13`.

## 1. Estabilización

- [ ] **AV-S-01** Actualizar `HANDOFF.md` (notas internas, fuera de Git) con HEAD actual, conteos reales y estado del push (AV-P1-04).
- [ ] **AV-S-02** Añadir filas v3 a `ROADMAP.md` con IDs nuevos: biblioteca, renombrar/eliminar, recalcular hablantes, exportar con vista previa, volumen 300 %, Material 3, PWA. Sin tocar IDs existentes.
- [ ] **AV-S-03** Entrada `[Unreleased]` en `CHANGELOG.md` con el trabajo v3 (AV-P1-04).
- [ ] **AV-S-04** Corregir los cuatro enlaces de imagen del README (AV-P2-06).
- [ ] **AV-S-05** Reproducir y corregir las filas en blanco de la revisión, con transcripción sintética (AV-P1-05).
- [ ] **AV-S-06** Validación de `Host` en el servidor local (AV-P1-02), con prueba de rebinding.
- [ ] **AV-S-07** Registrar en log el fallo del worker de jobs y marcar el job como fallido (AV-P1-03), con prueba.
- [ ] **AV-S-08** Acceso directo portable: `Exec` con `voz` o regeneración al arrancar; `exists()` validado; función de eliminar (AV-P1-01, AV-P2-12).
- [ ] **AV-S-09** Pin y checksum del instalador de uv en los lanzadores (AV-P2-02).
- [ ] **AV-S-10** Advertencia al enlazar fuera de loopback (AV-P2-01).
- [ ] **AV-S-11** Fixture de aislamiento XDG y `HOME` en `conftest.py` (AV-P2-10).
- [ ] **AV-S-12** Consolidar `_error`, `_UNSAFE_BIDI_CLASSES` y validadores duplicados (AV-P2-03, AV-P2-04, AV-P2-05), en cortes separados.
- [ ] **AV-S-13** Actualizar `source-map-js` dentro del lock (AV-P2-08) y repetir `npm audit --omit=dev`.

## 2. Migración de nombre (estrategia B)

- [ ] **AV-N-01** ADR que fije la estrategia B y la lista de lo que no cambia (`voz` como paquete, rutas XDG, `voz.sqlite3`, formato JSON).
- [ ] **AV-N-02** Búsqueda de disponibilidad del nombre "AV" por parte del propietario (fuera de esta auditoría).
- [ ] **AV-N-03** Comando `av` como alias de `voz`; test que ambos ejecutan el mismo `main`.
- [ ] **AV-N-04** Lectura de `AV_*` además de `VOZ_*`, con `AV_*` preferido; tests de precedencia.
- [ ] **AV-N-05** Textos de UI, README y documentación con la marca nueva; `VOZ` queda en ADR y CHANGELOG históricos.
- [ ] **AV-N-06** Verificar que el acceso directo nuevo funciona tras el rename (depende de AV-S-08).

## 3. Infraestructura TTS

- [ ] **AV-T-01** Puerto `SpeechSynthesisProvider` en `application/ports/`, sin implementación (ver `07`).
- [ ] **AV-T-02** Entidad de síntesis y almacenamiento de audio generado en XDG, con hash y metadatos (sin rutas del host en la API).
- [ ] **AV-T-03** Registro de proveedores TTS con rechazo de duplicados, igual que ASR.
- [ ] **AV-T-04** Protocolo del subproceso TTS (stdin/stdout con prefijo, como `diarization/worker.py`), con cancelación matando el proceso.
- [ ] **AV-T-05** Entorno Python aislado para proveedores TTS (uv project separado), fuera del entorno principal.
- [ ] **AV-T-06** Contrato común de pruebas para proveedores TTS con transporte falso.

## 4. KittenTTS

- [ ] **AV-K-01** Decisión de licencia de pesos KittenTTS 2 (Stellon Labs Community License): revisión del texto completo y, si hay uso comercial, contrato (ver `13`). **Bloquea cualquier distribución.**
- [ ] **AV-K-02** Adaptador KittenTTS 0.8 (ONNX, CPU) en subproceso, fijando commit y hash de wheel (sin releases).
- [ ] **AV-K-03** Medición en hardware objetivo: RTF, RAM pico, primer audio, carga (sin cifras de CPU públicas).
- [ ] **AV-K-04** Adaptador KittenTTS 2 en entorno con PyTorch, solo si AV-K-01 lo permite para el uso previsto.
- [ ] **AV-K-05** Atribución: `NOTICE` actualizado con Apache-2.0 del código y avisos de los pesos (AGENTS.md regla 10).

## 5. UI TTS

- [ ] **AV-U-01** Pantalla de síntesis a partir de una transcripción, con voz, idioma y velocidad; estados de carga, error y cancelación.
- [ ] **AV-U-02** Reproducción del audio generado con la misma pieza de reproductor existente.
- [ ] **AV-U-03** Consentimiento explícito y etiqueta de audio generado para cualquier voz clonada.
- [ ] **AV-U-04** i18n es/en de todo lo nuevo; accesibilidad básica y teclado.

## 6. Model Manager unificado

- [ ] **AV-M-01** Un único catálogo para ASR, diarización y TTS con el mismo modelo de descriptor (revisión obligatoria, AV-P3-07).
- [ ] **AV-M-02** Descarga y verificación SHA-256 común; reanudación ya existente reutilizada.
- [ ] **AV-M-03** Vista única en la UI con tamaño, uso de disco y borrado con confirmación.

## 7. Benchmarks

- [ ] **AV-B-01** Extender `voz bench` (o `av bench`) a síntesis: RTF, RAM pico, primer audio.
- [ ] **AV-B-02** Corpus público o sintético licenciado para diarización (AV-P2-15).
- [ ] **AV-B-03** Protocolo de medición documentado en `docs/benchmarks.md` con hardware y versiones.
- [ ] **AV-B-04** Benchmarks GPU solo con autorización explícita del propietario.

## 8. TinyML y edge

- [ ] **AV-E-01** Medición de whisper.cpp tiny/base cuantizado en una SBC real (clase 2).
- [ ] **AV-E-02** Confirmar licencia y tamaño de microWakeWord antes de cualquier prueba (clase 3).
- [ ] **AV-E-03** Harness propio para clases 3 a 5, separado del producto principal.

## 9. Documentación

- [ ] **AV-D-01** ADR del rename (AV-N-01) y ADR de TTS (subproceso y entorno aislado).
- [ ] **AV-D-02** ADR de decisión sobre Tauri antes de la fase 1 (AV-P2-14).
- [ ] **AV-D-03** Guía de contribución y plantillas al día con la UI v3.
- [ ] **AV-D-04** Documento de riesgos de exposición LAN y autenticación local (AV-P2-01).

## 10. Release

- [ ] **AV-R-01** Dry-run de `release-dry-run.yml` ejecutado (hoy no ejecutado, PKG-005).
- [ ] **AV-R-02** Acceso directo y lanzadores probados a mano en Windows y macOS (hoy solo CI).
- [ ] **AV-R-03** Decisión de primera release y de publicar el repositorio: **requiere autorización explícita del propietario** (S15.14, S16.20).
- [ ] **AV-R-04** Firma y notarización de macOS y Windows (plan Tauri, sección de costes): **requiere presupuesto**.
