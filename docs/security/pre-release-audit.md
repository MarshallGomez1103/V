# Auditoría previa a abrir el repositorio (S16.19)

- Fecha: 2026-09-30
- Alcance: árbol de trabajo (archivos versionados y no ignorados) **y** todo el
  historial git alcanzable (`--all`: 21 commits, una sola persona como autora).
- Herramienta: [`scripts/audit-secrets.sh`](../../scripts/audit-secrets.sh)
  (bash + git, sin dependencias nuevas; nunca imprime un secreto, solo
  `tipo commit ruta`).
- Este informe no reproduce ningún valor sensible. No se encontró ninguno que
  reproducir.

## Resultado

**0 hallazgos HIGH. Nada bloquea abrir el repositorio por secretos o datos
privados.** Quedan 19 hallazgos REVIEW (coincidencias dentro de `tests/`),
triados a mano abajo: todos son datos falsos o rutas genéricas, y una decisión
pendiente de autoría (ver "Decisión antes de publicar").

| Comprobación | Método | Resultado |
| --- | --- | --- |
| Claves de OpenAI/Anthropic (`sk-`), ElevenLabs (`sk_`, cabecera `xi-api-key` con valor), Hugging Face (`hf_`), AWS (`AKIA`/`ASIA`), GitHub (`ghp_`, `github_pat_`…), Slack, Google (`AIza`), bloques de clave privada, `Bearer …`, asignaciones literales `api_key/secret/token/password = "…"` | `git grep` sobre el árbol y `git log --all -G` sobre todo el historial (incluye líneas borradas) | Solo 3 valores falsos en tests (abajo). Ninguna clave real en el árbol ni en el historial. |
| Archivos de secretos (`.env*`, `*.key`, `*.pem`, `*.p12`, `credentials*.json`, `id_rsa*`, `id_ed25519*`) | nombres en el árbol y en todos los commits | Ninguno, en ningún momento. `.env.example` estaría permitido y tampoco existe. |
| `.ai/` nunca versionado | `git ls-files .ai`, `git log --all -- .ai`, `git check-ignore` | 0 archivos rastreados, 0 commits, ignorado por `.gitignore`. |
| Medios, bases de datos, modelos y archivos comprimidos | extensiones sobre árbol e historial (`wav`, `mp3`, `sqlite*`, `db`, `onnx`, `gguf`, `zip`…) | Solo los 6 fixtures sintéticos de `tests/fixtures/media/` (unos 20 KB en total, procedencia y licencia en [fixtures-licenses.md](../fixtures-licenses.md)). Ninguna base, modelo ni grabación. |
| Archivos grandes | `git ls-tree -r -l HEAD` y todos los blobs del historial, umbral 1 MiB | Ninguno. El mayor es el bundle web compilado (253 KB); el paquete git completo pesa unos 750 KiB. |
| Rutas personales del host en archivos versionados (`/home/<usuario>`, `/var/home/<usuario>`, `/Users/<usuario>`) | `git grep` y `git log --all -G` | Ninguna en código ni docs. Solo rutas inventadas en tests (abajo). Ni la del mantenedor ni ninguna real. |
| Datos personales en archivos | correos, URLs con `token=`/`key=` | Ningún correo en archivos versionados; ninguna URL con credenciales. |
| Archivos locales presentes pero ignorados (`.idea/`, `.directory`, `dist/`, caches, `.venv/`) | `git ls-files --others --ignored` | Ninguno parece un secreto; ninguno está rastreado ni lo estuvo. |

## Triaje de los hallazgos REVIEW

Claves con forma de `sk-` (3 archivos): son
literales de prueba obviamente falsos (empiezan por palabras como `secret`,
`super` o `test`, con un alfabeto pequeño) que sirven para comprobar que VOZ
**no** los filtra a logs ni a diagnósticos.

- `tests/unit/test_doctor.py`, `tests/unit/infrastructure/test_secrets.py`,
  `tests/integration/test_providers_api.py`.

Rutas con forma de ruta personal (7 archivos): son directorios de usuario
inventados (`student`, `usuario-real`, `host`, `u`, `x`, `secret` bajo `/home`)
usados para probar que VOZ rechaza o redacta rutas del host.

- `tests/unit/test_xdg_paths.py`, `tests/unit/test_diagnostics_bundle.py`,
  `tests/unit/test_doctor.py`, `tests/unit/application/test_model_tasks.py`,
  `tests/unit/domain/test_media_asset.py`,
  `tests/unit/infrastructure/cloud/test_elevenlabs_scribe.py`,
  `apps/web/src/components/Waveform.test.tsx`.

El script marca como REVIEW (no HIGH) todo lo que cae bajo `tests/`; si un valor
de test deja de ser obviamente falso, pasa a revisión humana.

## Decisión antes de publicar

**Metadatos de autoría.** El historial contiene un único autor, con el nombre
real del mantenedor y un **correo institucional** en los 21 commits (autor y
committer). Al publicar el historial ese correo queda público y es práctica-
mente imposible retirarlo después. Opciones, a elegir por el mantenedor:

1. Aceptarlo (es su identidad pública en `LICENSE`).
2. Reescribir el historial **antes** del primer push público con un correo
   `noreply` de GitHub (`git filter-repo --mailmap`, o `git rebase` con
   `--exec 'git commit --amend --reset-author'`) y configurar
   `git config user.email` con esa dirección desde ahora. Reescribir cambia
   todos los hashes citados en la documentación interna; hazlo una sola vez.

Esto no es un secreto, pero es el único dato personal que la auditoría encontró.

## Limitaciones

- Las expresiones son heurísticas: detectan formatos conocidos y asignaciones
  literales, no secretos arbitrarios sin formato (una contraseña de 12 letras
  en un YAML). Complementa con un escáner dedicado (gitleaks o trufflehog) si se
  dispone de él; no se añadió como dependencia.
- Solo se escanean diffs de texto (`-I`): los 6 fixtures binarios se comprobaron
  por nombre, tamaño y procedencia, no por contenido.
- Se auditan las referencias alcanzables (`--all`: ramas, remotos y tags). No se
  auditan el reflog ni objetos inalcanzables: no se publican con un `push`.
- El árbol incluye el trabajo aún sin commit de otros agentes de la oleada
  (archivos nuevos no ignorados); se vuelve a comprobar con el script antes del
  release.

## Cómo repetirla

```bash
scripts/audit-secrets.sh              # árbol + historial; sale con 1 si hay HIGH
scripts/audit-secrets.sh --tree-only  # solo el árbol (rápido, para antes de commitear)
```

Antes del primer push público: ejecútala sobre el estado final, revisa cada
REVIEW nuevo y confirma que la salida termina en `0 HIGH`. `.gitignore` ya cubre
`.env*`, claves, bases, medios y modelos; el script existe para detectar lo que
se haya colado igualmente (por ejemplo con `git add -f`).
