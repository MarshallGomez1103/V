# 00 · Índice — Auditoría integral de V

| Campo | Valor |
|---|---|
| Proyecto | **V** (paquete Python `voz`) |
| Repositorio | `https://github.com/<propietario>/V` |
| Rama | `main` (igual a `origin/main`) |
| HEAD auditado | `96284c53bc628dac330b222c4fde78ff3db9e2c9` |
| Fecha | 2026-10-21 |
| Estado Git inicial | `## main...origin/main`, árbol limpio, un solo worktree |
| Estado Git final | `## main...origin/main`, árbol limpio, HEAD sin cambios (comprobado al cerrar) |
| Archivos inventariados | 904 (`git ls-files`), cada uno con un área propietaria |
| Tipo de auditoría | Estática, de solo lectura. No se ejecutaron pruebas, builds ni servidores |
| Equipo | Revisión central + 8 instancias **de investigación** (Haiku) en paralelo, más 1 de segunda lectura |

## Cobertura

| Área (investigación) | Asignados | Profunda | Superficial | Omitidos | ~Líneas |
|---|---:|---:|---:|---:|---:|
| `informe_domain` | 19 | 19 | 0 | 0 | 1 700 |
| `informe_application` | 87 | 19 | 68 | 0 | 9 820 |
| `informe_speech` | 26 | 15 | 11 | 0 | 5 479 |
| `informe_tts_cloud` | 35 | 29 | 6 | 0 | 7 798 |
| `informe_persistence_jobs` | 34 | 10 | 22 | 2 | 6 080 |
| `informe_interfaces` | 90 | 33 | 57 (50 = bundle compilado) | 0 | 12 515 |
| `informe_frontend` | 236 | 40 | 141 | 55 (SCSS y catálogos i18n) | 35 349 |
| `informe_quality` | 318 | 19 | 247 + 30 en segunda lectura (ADR, docs/api, docs/architecture) | 22 (binarios, iconos, licencias) | 70 304 (incluye lockfiles) |
| revisión central (contexto) | 59 | — | — | — | 13 919 |
| **Total** | **904** | **184** | **552 + 30** | **79** | — |

No se auditó el 100 % del código. Los criterios de cada nivel y los motivos de omisión están en `13_INVENTARIO_ARCHIVOS.md` y en `11` §E.

## Informes

- [01 · Dominio](01_INFORME_DOMAIN.md)
- [02 · Aplicación y puertos](02_INFORME_APPLICATION.md)
- [03 · STT, audio y diarización](03_INFORME_SPEECH.md)
- [04 · TTS, nube y consentimiento](04_INFORME_TTS_CLOUD.md)
- [05 · Persistencia, jobs y concurrencia](05_INFORME_PERSISTENCE_JOBS.md)
- [06 · Interfaces: API, CLI y composición](06_INFORME_INTERFACES.md)
- [07 · Frontend](07_INFORME_FRONTEND.md)
- [08 · Calidad, CI y empaquetado](08_INFORME_QUALITY.md)
- [09 · Matriz de trazabilidad](09_MATRIZ_TRAZABILIDAD.md)
- [10 · Preparación para STT en tiempo real](10_STT_REALTIME_READINESS.md)
- [11 · Contradicciones y limitaciones (+ segunda lectura de ADR)](11_CONTRADICCIONES_Y_LIMITACIONES.md)
- [12 · Resumen para AEVA](12_RESUMEN_PARA_AEVA.md)
- [13 · Inventario de archivos](13_INVENTARIO_ARCHIVOS.md)

**Para empezar:** leer `12`, luego `09` y `10`, y consultar los informes 01–08 como evidencia.

## Limitaciones

- Sin ejecución: todo comportamiento en tiempo de ejecución es hipótesis.
- Subagentes en Haiku. Las citas se validaron por existencia (1056) y 15 evidencias clave se comprobaron a mano.
- Una consulta de solo lectura a la API de GitHub para el estado de CI. Evidencia de terceros (uvicorn instalado) en `06`.
- Cuatro informes los guardó la revisión central a partir del mensaje literal de su investigación.
- Este paquete describe debilidades de seguridad de un repositorio público: compartirlo de forma privada.

Detalle completo en `11_CONTRADICCIONES_Y_LIMITACIONES.md`.
