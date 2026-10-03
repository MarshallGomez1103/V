# Plan: VOZ como aplicación de escritorio con Tauri

Estado: **plan, nada implementado**. Hoy VOZ se abre con un lanzador de doble
clic (`Iniciar-*`) que arranca el servidor local y abre el navegador. Este
documento describe cómo empaquetarlo como aplicación instalable (ventana propia,
icono, instalador por sistema) con [Tauri 2](https://v2.tauri.app), qué cuesta y
qué riesgos tiene.

## Qué gana el usuario

- Un instalador por sistema (`.msi`/`.exe` en Windows, `.dmg` en macOS,
  `.AppImage`/`.deb`/`.rpm` en Linux) en vez de clonar el repo.
- Ventana propia sin barra del navegador, icono en el dock/barra de tareas y
  en el menú de aplicaciones.
- Cerrar la ventana cierra VOZ: no queda un servidor huérfano ni una terminal
  abierta.
- Actualizaciones desde la propia app (plugin `updater`).

## Arquitectura propuesta

```text
┌──────────── Tauri (Rust, ~10 MB) ─────────────┐
│  ventana WebView ── carga http://127.0.0.1:P  │
│  ciclo de vida: arranca / vigila / cierra     │
└───────────────┬───────────────────────────────┘
                │ sidecar (proceso hijo)
┌───────────────▼───────────────────────────────┐
│  servidor VOZ (Python: FastAPI + jobs + ASR)  │
│  el mismo de hoy, sin cambios de dominio      │
└───────────────────────────────────────────────┘
```

El backend sigue siendo Python: Faster Whisper, CTranslate2 y sherpa-onnx no
tienen equivalente razonable en Rust, y reescribirlos no aporta nada. Tauri solo
es la carcasa. La UI React/Carbon se reutiliza tal cual.

### Ciclo de vida

1. Tauri elige un puerto libre y un token aleatorio y arranca el sidecar:
   `voz serve --no-browser --port P` con `VOZ_DESKTOP_TOKEN=<token>`.
2. Muestra una pantalla de carga propia mientras sondea `/api/health`
   (hoy tarda ~1 s; la primera vez incluye la migración de la base).
3. Navega la ventana a `http://127.0.0.1:P`.
4. Al cerrar la ventana: `POST /api/shutdown` (ya existe para el botón Cerrar
   servidor); si en 5 s no terminó, mata el proceso. Un job en curso queda
   recuperable, como hoy con Ctrl+C.
5. Plugin `single-instance`: un segundo doble clic enfoca la ventana existente
   (hoy el CLI ya reutiliza el servidor abierto).
6. Si el sidecar muere, la ventana muestra "VOZ se detuvo" con botón
   Reiniciar y el final del log.

### Seguridad

- El servidor solo escucha en `127.0.0.1`, como hoy.
- El token del paso 1 se exige en las rutas peligrosas (`/api/shutdown`,
  claves cloud), además de la cabecera anti-CSRF actual; así otra web abierta
  en el navegador del usuario no puede apagar VOZ ni leer claves.
- CSP de Tauri limitada a `127.0.0.1:P`; sin `shell` abierto a la web.

## El problema grande: Python y las dependencias pesadas

| Pieza | Tamaño aproximado |
| --- | --- |
| Carcasa Tauri | ~10 MB |
| CPython standalone + VOZ + FastAPI | ~50 MB (medido en el AppImage base: 46 MiB) |
| faster-whisper + CTranslate2 + onnxruntime + sherpa-onnx | ~250 MB |
| Wheels CUDA (cuBLAS + cuDNN, solo Windows/Linux con NVIDIA) | ~1,3 GB comprimidos, 2,2 GB instalados |
| FFmpeg estático | ~50-70 MB |
| Modelos Whisper (turbo ~1,6 GB, large-v3 ~3 GB) | se descargan dentro de la app |

Tres formas de llevar Python, de menos a más trabajo:

1. **Sidecar "uv" (recomendada para empezar)**: el instalador lleva `uv` (un
   binario de ~30 MB) y el código de VOZ con su `uv.lock`. En el primer
   arranque, `uv sync` baja Python y las dependencias a la carpeta de datos de la
   app, con una pantalla de progreso. Es exactamente lo que hacen hoy los
   lanzadores, así que está probado en los tres sistemas por el CI. Instalador
   pequeño (~50 MB); la primera apertura necesita Internet.
2. **Python congelado (PyInstaller/Nuitka) como sidecar**: un ejecutable por
   sistema con todo dentro salvo CUDA y modelos. Instalador de ~300-400 MB,
   funciona sin Internet salvo para los modelos. Cuesta mantener los hooks de
   CTranslate2/onnxruntime y firmar muchos binarios.
3. **Todo dentro, incluido CUDA**: instalador de ~1,5 GB. No vale la pena: la
   mayoría de equipos no tienen NVIDIA, y los que sí pueden bajarlo después.

En las tres, CUDA se descarga aparte y solo si hay GPU NVIDIA (`nvidia-smi`
presente), y los modelos se siguen bajando desde el gestor de modelos.

## Firmas y avisos del sistema

- **Windows**: sin firma, SmartScreen avisa "Windows protegió su PC". Un
  certificado de firma de código cuesta ~100-400 USD/año (o Azure Trusted
  Signing, más barato). Defender puede marcar el FFmpeg descargado o el sidecar;
  firmar reduce eso.
- **macOS**: sin firmar y notarizar, Gatekeeper bloquea la app. Requiere cuenta
  de Apple Developer (99 USD/año). Cada binario dentro (sidecar, `.so`/`.dylib`
  de Python, FFmpeg) debe ir firmado; con la opción 1, lo que baja `uv` en el
  primer arranque no está firmado por nosotros: hay que comprobar que Gatekeeper
  lo permite (los wheels de PyPI suelen estar bien; el FFmpeg descargado hay que
  probarlo).
- **Linux**: AppImage, `.deb` y `.rpm` sin firma obligatoria. En Bazzite/Fedora
  Atomic lo natural es AppImage o Flatpak (ya hay prototipos medidos en
  [appimage-flatpak.md](appimage-flatpak.md)).

## Riesgos concretos

- **WebView distinto por sistema**: Tauri usa WebView2 (Windows, Chromium),
  WKWebView (macOS, Safari) y WebKitGTK (Linux). La UI hoy solo se prueba en
  Chrome. Riesgo principal: **reproducir audio AAC/M4A en WebKitGTK** depende de
  los plugins de GStreamer del sistema. Mitigación: que el reproductor use el
  WAV/derivado normalizado que VOZ ya genera, o servir audio transcodificado.
- **Arranque en frío** de la opción 1: la primera vez tarda minutos. Necesita
  una pantalla de progreso honesta (qué baja, cuánto falta).
- **Antivirus y rutas largas en Windows**: `.venv` profundo dentro de
  `%LOCALAPPDATA%`; vigilar el límite de 260 caracteres.
- **Dos copias de la verdad**: los lanzadores `Iniciar-*` y la app deben
  compartir la misma carpeta de datos (ya resuelta por `paths.py`) para que un
  usuario pueda pasar de uno a otro sin perder proyectos.

## Fases y esfuerzo estimado

| Fase | Qué | Esfuerzo |
| --- | --- | --- |
| 0 | **App instalable sin Tauri**: manifest PWA para que Chrome/Edge ofrezcan "Instalar VOZ" (ventana propia e icono) sobre el servidor local actual | 1 tarde |
| 1 | Carcasa Tauri en `apps/desktop/`: ventana, sidecar con `uv` (opción 1), pantalla de carga, cierre limpio, single-instance, token | 3-5 días |
| 2 | Primer arranque guiado: progreso de `uv sync`, detección NVIDIA y CUDA opcional, errores claros sin Internet | 2-3 días |
| 3 | CI con `tauri-action` en Windows, macOS y Linux que construye instaladores sin firmar y ejecuta un humo (abrir, `/api/health`, cerrar) | 2 días |
| 4 | Firma y notarización (requiere comprar certificados), updater con releases de GitHub | 2-3 días + trámites |
| 5 | Opcional: Python congelado (opción 2) para instalar sin Internet | 1-2 semanas |

Recomendación: hacer la fase 0 ya (casi gratis, da el efecto "aplicación" en
Windows, macOS y Linux) y la 1-3 cuando se quiera publicar. La firma (fase 4)
solo tiene sentido con la release pública.

## Qué no cambia

- El dominio, la API y la UI. Tauri no exige tocar el backend salvo el token
  opcional de la sección de seguridad.
- Los lanzadores `Iniciar-*` siguen siendo la forma de usar VOZ desde el código
  fuente y la de desarrollo.
