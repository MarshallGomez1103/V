# Desarrollo de VOZ en Bazzite

Esta guía prepara un entorno de desarrollo sin modificar la imagen base de
Bazzite. VOZ está todavía en fase de skeleton: los comandos documentados aquí
son el contrato de desarrollo esperado y cada paso debe contrastarse con el
estado de [ROADMAP.md](../../ROADMAP.md).

## Principios para Bazzite/Fedora Atomic

- Evitar `rpm-ostree install` para herramientas ordinarias de desarrollo.
- Preferir herramientas en espacio de usuario o un contenedor Distrobox.
- No usar Docker/Podman como requisito para ejecutar VOZ con GPU.
- Mantener modelos y datos en los directorios XDG del usuario, nunca dentro de
  una imagen de contenedor o del repositorio.
- No instalar Whisper ni descargar modelos durante el bootstrap del skeleton.
- No reiniciar, rebasar la imagen del sistema ni cambiar drivers como parte de
  esta guía.

## Requisitos del bootstrap

Comprueba primero qué está disponible; no reinstales herramientas que ya
funcionan.

```bash
git --version
uv --version
node --version
npm --version
```

Para la etapa de ingestión multimedia también harán falta `ffmpeg` y `ffprobe`,
pero no son necesarios para demostrar el skeleton HTTP/UI de la Sección 1:

```bash
ffmpeg -version
ffprobe -version
```

Versiones objetivo del proyecto:

- Python 3.12, administrado por `uv`;
- Node.js compatible con la versión declarada por el frontend;
- npm usando el lockfile versionado.

No se debe depender del Python del sistema ni ejecutar `sudo pip install`.

## Opción A: herramientas de usuario

Esta es la ruta más corta cuando `uv`, Node y npm ya están disponibles en el
usuario. Desde la raíz del checkout:

```bash
uv sync --all-groups
cd apps/web
npm ci
npm run build
cd ../..
uv run pytest
uv run voz --no-browser
```

La URL objetivo es `http://127.0.0.1:8765`. Mientras el bootstrap no esté
completo, consulta los IDs S1.* en el roadmap: no todos los comandos tienen que
existir todavía.

## Opción B: Distrobox de desarrollo

Usa Distrobox cuando prefieras aislar toolchains o dependencias multimedia. La
carpeta de trabajo y los directorios XDG siguen perteneciendo al usuario del
host.

Ejemplo conceptual:

```bash
distrobox create --name voz-dev --image fedora:latest
distrobox enter voz-dev
```

Dentro del contenedor instala únicamente los prerequisitos de desarrollo que
falten, siguiendo la documentación oficial de cada herramienta, y luego ejecuta
los mismos comandos de la Opción A. No guardes modelos en capas del contenedor.

Las pruebas con CUDA deben tratarse como una actividad separada: primero se
verifica que el contenedor ve la GPU y luego se instala el stack declarado por
el proyecto. No se debe cambiar el driver del host para acomodar una dependencia
sin una decisión explícita y evidencia del problema.

## Desarrollo con frontend y backend separados

Durante desarrollo, dos terminales pueden ejecutar los procesos por separado.
Los scripts exactos quedan sujetos al bootstrap:

Terminal 1:

```bash
uv run voz --no-browser
```

Terminal 2:

```bash
cd apps/web
npm run dev
```

El frontend debe usar la configuración de desarrollo versionada para contactar
la API local. No codifiques rutas absolutas ni direcciones LAN.

## Comprobaciones de calidad

Backend:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

Frontend:

```bash
cd apps/web
npm run lint
npm run typecheck
npm run test
npm run build
```

La verificación limpia de la Sección 1 exige probar desde un checkout nuevo o un
entorno vacío. Crear archivos no basta: `voz` debe iniciar, `/api/health` debe
responder y la Home debe cargarse en `127.0.0.1`. Registra el entorno y los
comandos realmente ejecutados en el handoff local antes de marcar S1.22.

## Directorios de ejecución

VOZ deberá respetar estas ubicaciones Linux:

```text
~/.config/voz/config.toml
~/.local/share/voz/voz.db
~/.local/share/voz/projects/
~/.local/share/voz/models/
~/.cache/voz/
~/.local/state/voz/logs/
```

Estos datos no se versionan. Un entorno de prueba debe poder redirigir las
variables XDG a un directorio temporal para no contaminar datos reales.

## Resolución de problemas del bootstrap

### `uv` usa un Python incorrecto

Comprueba la versión resuelta con `uv run python --version`. Corrige la
declaración del proyecto o permite que `uv` obtenga Python 3.12; no sustituyas el
Python del host.

### El puerto 8765 está ocupado

Comprueba el proceso existente y usa el flag documentado:

```bash
uv run voz --no-browser --port 9000
```

No termines procesos desconocidos automáticamente.

### La UI no carga

Verifica por separado:

1. que `/api/health` responde;
2. que el build del frontend termina sin errores;
3. si se ejecuta en modo desarrollo o como bundle servido por la API;
4. que la URL usa `127.0.0.1` y el puerto mostrado por la CLI.

### FFmpeg no está disponible

Esto bloquea la futura ingestión, no el skeleton. Registra el diagnóstico y
elige una instalación de usuario o Distrobox. No añadas layering del sistema
base como respuesta automática.

## Criterio de salida

El setup de Bazzite se considera verificado únicamente cuando un checkout limpio
permite instalar dependencias, ejecutar las comprobaciones relevantes, iniciar
`voz` y abrir la UI local. Hasta entonces la documentación puede estar completa,
pero el item de verificación S1.22 debe permanecer pendiente.
