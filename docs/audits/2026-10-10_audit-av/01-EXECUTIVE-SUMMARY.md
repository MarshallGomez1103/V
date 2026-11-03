# 01 · Resumen ejecutivo — Auditoría VOZ/AV

Fecha: 2026-10-10 · Repositorio: `<repo-V>` · Rama `main`, HEAD `1186908` (2026-10-03), igual a `origin/main`, árbol limpio antes y después de la auditoría.

Alcance: auditoría de solo lectura. No se modificó código, no hubo commits, push, descargas de modelos, llamadas a proveedores cloud ni benchmarks GPU. Los únicos comandos que escriben son caches de herramientas (ruff, pyright, vite) y los informes en `.ai/audit-av/` (ignorado por Git, comprobado).

## Estado general

VOZ está en un estado **técnicamente sólido en lo que se puede verificar desde el código**: todos los checks oficiales pasan, la arquitectura hexagonal se sostiene (cero violaciones de capa, cero ciclos entre módulos) y el bundle del frontend es reproducible byte a byte. El problema principal no es de código sino de **documentación desfasada** y de **algunas decisiones de seguridad y empaquetado que solo funcionan en el entorno de desarrollo**.

| Área | Veredicto | Evidencia clave |
|---|---|---|
| Build y calidad | Verde | ruff, format, pyright estricto, eslint, tsc, vitest, build reproducible |
| Tests | 1612 backend + 543 frontend pasan | pytest aislado exit 0; vitest 59 archivos |
| Arquitectura | Sana | 160 módulos, 488 aristas, 0 violaciones, 0 ciclos |
| STT local | Completo y recuperable | Chunks de 30 min, checkpoints SQLite, cancelación en 6 puntos |
| UI | Funcional, mejorable | Home verificada en escritorio y 390 px; 125 `aria-*`; virtualización |
| Linux / escritorio | **Frágil** | Acceso directo con rutas absolutas al checkout |
| Seguridad local | Aceptable con brechas | Sin validación de `Host` ni token (ADR-0006 lo asume) |
| Documentación de estado | **Desfasada** | HANDOFF y ROADMAP no recogen el trabajo v3 |

## Fortalezas

- Suite de tests amplia y en verde en CI para Linux, Windows y macOS (último run de `main`, 37177276110, todos los jobs en `success`).
- Límites de capa respetados: el dominio no importa frameworks y la aplicación no importa infraestructura ni interfaces.
- Cancelación y recuperación pensadas desde el dominio: `JobRunner.cancel` (job_runner.py:273), checkpoints por chunk y `recover()` al arrancar.
- Privacidad por defecto: bind a 127.0.0.1, sin CORS, cloud solo con clave y selección explícita, apagado protegido por cabecera personalizada.
- Diarización aislada en subproceso por una razón documentada (el GIL de sherpa-onnx): precedente útil para TTS.
- Auditoría de secretos del historial completo: 0 HIGH.

## Problemas (priorizados; detalle en `11-TECHNICAL-DEBT.md`)

**No se ha verificado ningún P0** (bloqueo que impida usar el producto).

P1 — corregir antes de ampliar (5, de los cuales 3 verificados):
1. **AV-P1-01** Acceso directo de escritorio con rutas absolutas del checkout. Al mover el proyecto el icono queda roto y la UI sigue diciendo que existe. *Verificado.*
2. **AV-P1-02** API local sin validación de `Host`: posible lectura de la biblioteca desde una página web maliciosa (DNS rebinding). *Parcial: por lectura de código, no explotada.*
3. **AV-P1-03** El worker de jobs traga cualquier excepción sin log (`job_runner.py:319`). *Verificado.*
4. **AV-P1-04** HANDOFF, ROADMAP y CHANGELOG describen el estado de hace una semana: el trabajo v3 (biblioteca, renombrar/eliminar, recalcular hablantes, Material 3) no aparece en ninguno. *Verificado.*
5. **AV-P1-05** Filas de segmento en blanco tras seek y autoscroll, según HANDOFF. *No verificado en esta auditoría.*

P2 — mejora planificada: exposición LAN sin autenticación (documentada), `curl | sh` sin pin en los lanzadores, helpers duplicados, cuatro enlaces rotos en el README, bundle JS de 752 KB en un solo chunk, vulnerabilidad alta transitiva en `source-map-js` (npm audit), y gobernanza de Tauri sin ADR.

## Prioridades recomendadas

1. Documentación al día (AV-P1-04): es barata, desbloquea al arquitecto y evita decisiones sobre datos falsos.
2. Acceso directo portable y validación de `Host` (AV-P1-01, AV-P1-02): son las dos brechas que el usuario final notaría.
3. Log y fallo explícito en el worker (AV-P1-03).
4. Decisiones de producto pendientes antes de TTS: licencia de los pesos KittenTTS 2 y estrategia de rename VOZ → AV (ver `13-HANDOFF-FOR-ARCHITECT.md`).

## Lo que no se pudo verificar

- Funcionamiento real del ASR con GPU en esta sesión (requiere modelos; no se descargaron ni se ejecutaron benchmarks).
- Proveedores cloud contra el servicio real (solo fakes; no se usó ninguna API de pago).
- Ejecución manual en Windows y macOS (solo CI).
- Instalación del acceso directo desde la UI y su eliminación: no ejecutadas.
- Auditoría de dependencias de Python (no hay `pip-audit` instalado; no se instaló para no modificar el entorno).

## Archivos de este paquete

Ver el índice en `13-HANDOFF-FOR-ARCHITECT.md`, sección "Referencias". Evidencia en bruto en `evidencia/`.
