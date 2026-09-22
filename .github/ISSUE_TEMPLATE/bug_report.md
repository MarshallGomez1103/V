---
name: Reporte de bug
about: Reportar un comportamiento incorrecto reproducible en VOZ
title: "[bug] "
labels: bug
---

## Descripción

Describe el comportamiento incorrecto de forma clara y concisa.

## Pasos para reproducir

1. ...
2. ...
3. ...

## Comportamiento esperado

Qué esperabas que pasara.

## Comportamiento observado

Qué pasó realmente. Incluye mensajes de error o códigos estables si los hay.

## Entorno

- Commit o rama de VOZ:
- Sistema operativo:
- Versión de Python (`python --version`) y de Node (`node --version`):
- ¿Instalaste el extra `asr-local`? ¿Con qué modelo/provider?

## Evidencia

Adjunta logs relevantes (redacta rutas privadas y secretos) o una captura de
pantalla si aplica. **No adjuntes grabaciones, transcripciones ni datos
privados propios o de terceros.** Si necesitas un archivo de audio para
reproducir el bug, usa o crea un fixture sintético, como los documentados en
[`docs/fixtures-licenses.md`](../../docs/fixtures-licenses.md).

## ¿Es una regresión?

- [ ] Sí, funcionaba antes (indica en qué commit/versión, si lo sabes).
- [ ] No lo sé o no aplica.

## IDs de roadmap relacionados (opcional)

Si el bug está relacionado con un ID de `ROADMAP.md`, indícalo aquí
(por ejemplo `S4.12`).
