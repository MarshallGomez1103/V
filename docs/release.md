# Versionado y proceso de release

VOZ sigue [SemVer 2.0.0](https://semver.org/lang/es/). La versión vive en un solo
lugar de verdad, `pyproject.toml` (`[project] version`), y `src/voz/__init__.py`
(`voz.__version__`) debe coincidir: `tests/packaging/test_version_consistency.py`
lo comprueba y falla si divergen. El historial visible para usuarios está en
[CHANGELOG.md](../CHANGELOG.md).

## Reglas mientras la versión es 0.x

- Incrementar el **minor** (`0.2.0`) puede romper la API pública; el
  changelog lo indica en una sección "Cambiado" o "Eliminado".
- Incrementar el **patch** (`0.1.1`) solo corrige errores y no rompe la API pública.
- `1.0.0` se publicará cuando la API pública de abajo se considere estable; desde
  entonces se aplica SemVer estricto (romper compatibilidad exige un major).

## Qué cuenta como API pública

1. **CLI**: el comando `voz`, sus subcomandos (`serve`, `doctor`), sus opciones
   (`--host`, `--port`, `--no-browser`, `--json`, `--redact`) y sus códigos de salida.
2. **HTTP `/api`**: rutas, métodos, cuerpos, códigos de estado y códigos de error
   estables (`{"detail": {"code", "message"}}`) documentados en `docs/api/`.
3. **Formato JSON `voz.transcript` v1**: el documento exportado
   (`"format": "voz.transcript"`, `"version": 1`). Los cambios compatibles (campos
   nuevos opcionales) no suben su `version`; un cambio incompatible crea `version: 2`
   y el exportador sigue leyendo/emitiendo la anterior durante al menos un minor.
4. **Esquema de datos migrado**: la base SQLite bajo XDG y la disposición de
   directorios de proyecto. Toda modificación llega con una migración Alembic
   automática y sin pérdida de datos; una migración que no pueda conservar datos
   es un cambio incompatible.

No forman parte de la API pública: el código Python importable (`voz.*`), el
contenido del bundle web, los mensajes de log, el texto de `voz doctor` sin
`--json`, ni las funciones marcadas como experimentales (por ejemplo, la
transcripción con Faster Whisper real y CUDA hasta que se ejerciten en hardware).

## Construir artefactos (sin publicar)

```bash
export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
uv build --out-dir dist          # wheel + sdist
scripts/checksums.sh dist        # escribe y verifica dist/SHA256SUMS
scripts/check-reproducible-build.sh   # 3 builds, mismo SHA-256
scripts/check-install.sh dist/*.whl   # uv tool install + arranque fuera del checkout
```

Publicar una release (etiqueta, GitHub Release, PyPI) solo se hace con
autorización explícita del mantenedor y no forma parte de estos scripts.
