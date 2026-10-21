// V10-06S: maneja la UI real de V con Chrome headless por CDP y guarda capturas PNG en inglés.
// Lo lanza scripts/capture-screenshots.sh (servidor, datos, modelos y XDG temporales).
// Solo biblioteca estandar de Node >= 22 (WebSocket y fetch globales); sin dependencias.
import { spawn } from 'node:child_process'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { join } from 'node:path'

const env = (name) => {
  const value = process.env[name]
  if (!value) throw new Error('falta la variable ' + name)
  return value
}
const url = env('CAPTURE_URL')
const audioDir = env('CAPTURE_AUDIO_DIR')
const outDir = env('CAPTURE_OUT')
const profile = env('CAPTURE_PROFILE')
const model = env('CAPTURE_MODEL')
const hfLink = env('CAPTURE_HF_LINK')
const chromeCmd = (process.env.CHROME_CMD ?? 'flatpak run com.google.Chrome').split(' ')
const WIDTH = 1440
const HEIGHT = 1000

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function freePort() {
  return new Promise((resolve, reject) => {
    const server = createServer()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address()
      server.close(() => resolve(port))
    })
  })
}

async function launchChrome(port) {
  const args = [
    ...chromeCmd.slice(1),
    '--headless=new',
    '--disable-gpu',
    '--hide-scrollbars',
    '--no-first-run',
    '--no-default-browser-check',
    '--force-color-profile=srgb',
    ...(process.env.CHROME_NO_SANDBOX === '1' ? ['--no-sandbox'] : []),
    '--lang=en-US',
    `--user-data-dir=${profile}`,
    `--remote-debugging-port=${port}`,
    `--window-size=${WIDTH},${HEIGHT}`,
    'about:blank',
  ]
  const child = spawn(chromeCmd[0], args, { stdio: 'ignore' })
  for (let i = 0; i < 150; i += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/list`)
      const pages = (await response.json()).filter((t) => t.type === 'page')
      if (pages[0]) return { child, wsUrl: pages[0].webSocketDebuggerUrl }
    } catch {
      /* Chrome aun arrancando */
    }
    await sleep(200)
  }
  child.kill()
  throw new Error('Chrome no abrio el puerto de depuracion')
}

function connect(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl)
    let nextId = 1
    const pending = new Map()
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data)
      const waiter = message.id ? pending.get(message.id) : undefined
      if (!waiter) return
      pending.delete(message.id)
      if (message.error) waiter.reject(new Error(message.error.message))
      else waiter.resolve(message.result)
    }
    ws.onerror = () => reject(new Error('fallo el WebSocket de CDP'))
    ws.onopen = () =>
      resolve({
        send: (method, params = {}) =>
          new Promise((res, rej) => {
            const id = nextId++
            pending.set(id, { resolve: res, reject: rej })
            ws.send(JSON.stringify({ id, method, params }))
          }),
        close: () => ws.close(),
      })
  })
}

const chrome = await launchChrome(await freePort())
const cdp = await connect(chrome.wsUrl)
mkdirSync(outDir, { recursive: true })

// evalua una expresion en la pagina y devuelve su valor (JSON-serializable)
async function page(expression) {
  const { result, exceptionDetails } = await cdp.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  })
  if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? 'error en la pagina')
  return result.value
}

async function waitFor(expression, what, timeoutMs = 60000) {
  const limit = Date.now() + timeoutMs
  while (Date.now() < limit) {
    if (await page(`Boolean(${expression})`)) return
    await sleep(100)
  }
  throw new Error('tiempo agotado esperando: ' + what)
}

// alto de la ventana; la lista de segmentos mide en vh, asi que cambia el diseño
async function viewport(height) {
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width: WIDTH,
    height: Math.ceil(height),
    deviceScaleFactor: 1,
    mobile: false,
  })
  await sleep(500)
}

// guarda un PNG. Sin `region`: la ventana visible. Con `region`: una expresion de la
// pagina que devuelve {x, y, w, h} en coordenadas del documento (a escala 1).
async function shot(name, region) {
  const params = { format: 'png' }
  if (region) {
    const box = await page(region)
    if (!box) throw new Error('sin region para ' + name)
    params.captureBeyondViewport = true
    params.clip = { x: Math.max(0, box.x), y: Math.max(0, box.y), width: box.w, height: box.h, scale: 1 }
  }
  const { data } = await cdp.send('Page.captureScreenshot', params)
  const bytes = Buffer.from(data, 'base64')
  writeFileSync(join(outDir, name), bytes)
  console.log(`ok  ${name} (${Math.round(bytes.length / 1024)} KB)`)
}

// caja de un elemento en coordenadas del documento: [izquierda, arriba, derecha, abajo]
const BOX = `const box = (s) => {
  const e = typeof s === 'string' ? document.querySelector(s) : s
  const r = e.getBoundingClientRect()
  return [r.left + scrollX, r.top + scrollY, r.right + scrollX, r.bottom + scrollY]
}`

// recorte del ancho completo de la ventana, desde arriba hasta `selector` (+ margen)
const windowUntil = (selector, pad = 32) => `(() => { ${BOX}
  return { x: 0, y: 0, w: ${WIDTH}, h: box(${JSON.stringify(selector)})[3] + ${pad} }
})()`

const click = (selector) =>
  page(`document.querySelector(${JSON.stringify(selector)}).click()`)

const clickText = (tag, text, scope = 'document') =>
  page(`(() => {
    const el = [...${scope}.querySelectorAll(${JSON.stringify(tag)})].find(
      (e) => e.textContent.trim() === ${JSON.stringify(text)} && e.offsetParent !== null,
    )
    if (!el) throw new Error('sin ' + ${JSON.stringify(tag)} + ' ' + ${JSON.stringify(text)})
    el.click()
  })()`)

// clic de raton real en un punto vacio (margen izquierdo): quita el foco y los tooltips
async function clickEmpty() {
  for (const type of ['mousePressed', 'mouseReleased']) {
    await cdp.send('Input.dispatchMouseEvent', { type, x: 8, y: 400, button: 'left', clickCount: 1 })
  }
  await sleep(300)
}

// escribe con el teclado (CDP) sobre el campo: selecciona lo que haya y lo sustituye
async function typeInto(selector, text, { enter = false } = {}) {
  await page(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); e.focus(); e.select?.() })()`)
  await cdp.send('Input.insertText', { text })
  if (enter) {
    for (const type of ['keyDown', 'keyUp']) {
      await cdp.send('Input.dispatchKeyEvent', {
        type,
        key: 'Enter',
        code: 'Enter',
        windowsVirtualKeyCode: 13,
        ...(type === 'keyDown' ? { text: '\r' } : {}),
      })
    }
  }
}

// Los <select> nativos no abren su lista en headless: se elige la opcion y se emite el
// mismo evento `change` que manda el navegador al elegirla.
const choose = (selector, optionText) =>
  page(`(() => {
    const select = document.querySelector(${JSON.stringify(selector)})
    const option = [...select.options].find((o) => o.text.startsWith(${JSON.stringify(optionText)}))
    if (!option) throw new Error('sin opcion ' + ${JSON.stringify(optionText)})
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, option.value)
    select.dispatchEvent(new Event('change', { bubbles: true }))
  })()`)

// Los paneles de la UI (Carbon) son <section aria-labelledby="...-title">.
const panel = (id) => `section[aria-labelledby="${id}"]`

// Los botones de icono de la cabecera se identifican por su nombre accesible.
const header = (label) => `header button[aria-label="${label}"]`

// Importa un audio de demo por la pantalla «New transcription» y lo transcribe.
async function transcribe(file, title, { speakers = false } = {}) {
  await page(`location.hash = '#/nueva'`)
  await waitFor(`location.hash === '#/nueva' && document.querySelector('input[type=file]')`, 'la pantalla de importar')
  await sleep(400)
  // el audio se inyecta como un File real en el input de la zona de soltar
  const audioB64 = readFileSync(join(audioDir, file)).toString('base64')
  await page(`(async () => {
    const bytes = Uint8Array.from(atob(${JSON.stringify(audioB64)}), (c) => c.charCodeAt(0))
    const transfer = new DataTransfer()
    transfer.items.add(new File([bytes], ${JSON.stringify(file)}, { type: 'audio/wav' }))
    const input = document.querySelector('input[type=file]')
    input.files = transfer.files
    input.dispatchEvent(new Event('change', { bubbles: true }))
  })()`)
  await waitFor(`document.querySelector('button[type=submit]:not([disabled])')`, 'el archivo listo')
  await typeInto('main input[type=text]', title)
  await click('button[type=submit]')
  // tras importar, la pantalla pasa a la configuración (reproductor + motor + opciones)
  await waitFor(`document.getElementById('options-title')`, 'la configuracion')
  await waitFor(`document.querySelector('.voz-options input[type=radio]')`, 'las opciones de motor')
  await sleep(600)
  const chosen = await page(`(() => {
    for (const radio of document.querySelectorAll('.voz-options input[type=radio]')) {
      const tile = radio.closest('.cds--radio-tile__wrapper') ?? radio.closest('label')
      if (!radio.disabled && tile && tile.textContent.includes('Model: ' + ${JSON.stringify(model)})) {
        radio.click()
        return true
      }
    }
    return false
  })()`)
  if (!chosen) throw new Error('el motor ' + model + ' no esta disponible para iniciar')
  if (speakers) {
    await click('.voz-diarization button[role=switch]')
    await waitFor(`document.querySelector('.voz-diarization__ready')`, 'el modelo de hablantes listo')
  }
  await sleep(300)
  const started = Date.now()
  await clickText('button', 'Transcribe')
  await waitFor(
    `/complete|failed|cancel/i.test(document.getElementById('job-title')?.textContent ?? '')`,
    'el job de ' + title,
    180000,
  )
  const status = await page(`document.getElementById('job-title').textContent`)
  if (!/complete/i.test(status)) throw new Error(title + ': ' + status)
  await waitFor(`document.querySelectorAll('.segments li').length > 0`, 'los segmentos')
  console.log(`ok  ${title}: ${status} en ${((Date.now() - started) / 1000).toFixed(1)} s`)
  // el texto que se ve en las capturas es la salida real del modelo: queda en el log
  const lines = await page(`[...document.querySelectorAll('.segments li')].map((li) =>
    li.querySelector('.segment-seek')?.textContent.trim() + ' ' + li.querySelector('.segment-text')?.textContent.trim())`)
  for (const line of lines) console.log('    ' + line)
}

try {
  await cdp.send('Page.enable')
  // La UI elige idioma, tema y diseño de localStorage: inglés, Carbon White y Carbon.
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', {
    source: `try {
      localStorage.setItem('voz.lang', 'en')
      localStorage.setItem('voz.theme', 'white')
      localStorage.setItem('voz.design', 'carbon')
    } catch { /* sin almacenamiento */ }`,
  })
  await cdp.send('Emulation.setEmulatedMedia', {
    features: [{ name: 'prefers-color-scheme', value: 'light' }],
  })
  await viewport(HEIGHT)
  await cdp.send('Page.navigate', { url: url + '/#/' })
  await waitFor(`document.querySelector('h1') && document.querySelector('.voz-library')`, 'la pagina de inicio')

  // Tres proyectos reales para la biblioteca; el último es el espacio de trabajo.
  await transcribe('lecture-notes.wav', 'Lecture notes demo')
  await transcribe('podcast-intro.wav', 'Podcast intro demo', { speakers: true })
  await transcribe('product-sync.wav', 'Product sync', { speakers: true })

  // --- espacio de trabajo: hablantes con nombre, reproducción en pausa a mitad ---
  await waitFor(`document.querySelectorAll('input[id^=speaker-name-]').length === 2`, 'dos hablantes', 15000)
  const speakerInputs = await page(`[...document.querySelectorAll('input[id^=speaker-name-]')].map((e) => '#' + CSS.escape(e.id))`)
  await typeInto(speakerInputs[0], 'Lead', { enter: true })
  await sleep(600)
  await typeInto(speakerInputs[1], 'Writer', { enter: true })
  await sleep(600)
  await clickEmpty()
  // clic en el tiempo de un segmento: salta ahí y reproduce; se pausa enseguida
  await page(`document.querySelectorAll('.segments .segment-seek')[3].click()`)
  await sleep(900)
  await click(`${panel('audio-title')} .voz-player button.cds--btn--primary`)
  await clickEmpty()
  // ventana completa: alto de toda la página (dos pasadas, la lista mide en vh)
  for (let i = 0; i < 2; i += 1) await viewport(await page(`document.documentElement.scrollHeight`))
  await shot('v-workspace.png')

  // --- recorte: hablantes + reproductor, uno al lado del otro. La altura de la lista
  // cambia con el número de segmentos (Whisper en GPU no siempre corta igual): se prueba
  // sin filtro y filtrando a cada hablante, y se queda el estado en que el reproductor
  // y el panel de hablantes empiezan más a la par. El recorte empieza en el más bajo de
  // los dos (así no entra el panel de encima) y nunca por encima del último segmento. ---
  await viewport(2000) // mayor que la página: la lista queda en su tope fijo
  const filters = `[...document.querySelectorAll('${panel('speakers-title')} button[aria-pressed]')]`
  const setFilter = async (index) => {
    await page(`(() => {
      const buttons = ${filters}
      const pressed = buttons.find((b) => b.getAttribute('aria-pressed') === 'true')
      const wanted = ${index} < 0 ? null : buttons[${index}]
      if (wanted ? wanted !== pressed : pressed) (wanted ?? pressed).click()
    })()`)
    await sleep(600)
  }
  const gap = () => page(`(() => { ${BOX}
    return Math.abs(box(${JSON.stringify(panel('audio-title'))})[1] - box(${JSON.stringify(panel('speakers-title'))})[1])
  })()`)
  let best = { index: -1, gap: Infinity }
  for (let index = -1; index < (await page(`${filters}.length`)); index += 1) {
    await setFilter(index)
    const value = await gap()
    if (value < best.gap) best = { index, gap: value }
  }
  await setFilter(best.index)
  await clickEmpty()
  console.log(`    recorte de hablantes: filtro ${best.index}, desfase ${Math.round(best.gap)} px`)
  await shot('v-speakers-playback.png', `(() => { ${BOX}
    const audio = box(${JSON.stringify(panel('audio-title'))})
    const speakers = box(${JSON.stringify(panel('speakers-title'))})
    const seeks = document.querySelectorAll('.segments .segment-seek')
    const top = Math.max(audio[1] - 16, speakers[1] - 16, box(seeks[seeks.length - 1])[3] + 4)
    const bottom = Math.max(audio[3], speakers[3]) + 16
    return { x: audio[0] - 16, y: top, w: speakers[2] - audio[0] + 32, h: bottom - top }
  })()`)
  await setFilter(-1)

  // --- exportar: Markdown con tiempos y agrupado por hablante, con su vista previa ---
  await viewport(1250)
  await page(`scrollTo(0, 0)`)
  await clickText('button', 'Export')
  await waitFor(`document.querySelector('.voz-export__preview')`, 'la vista previa de exportar')
  await click('.voz-export input[value=markdown]')
  await sleep(400)
  for (const id of ['timestamps', 'group']) await click(`.voz-export button[role=switch][id$="-${id}"]`)
  await waitFor(`document.querySelector('.voz-export__preview')?.textContent.includes('## Lead')`, 'la vista previa agrupada')
  await sleep(600)
  await shot('v-export.png')
  await clickText('button', 'Close')
  await sleep(400)

  // --- biblioteca con la piel Material 3 (claro), elegida en Settings ---
  await viewport(HEIGHT)
  await page(`location.hash = '#/'`)
  await waitFor(`document.querySelectorAll('.voz-library tbody tr').length === 3`, 'la biblioteca con tres proyectos')
  const setDesign = async (design) => {
    await click(header('Settings'))
    await waitFor(`document.querySelector('.voz-choice__shape--${design}')`, 'el menu de ajustes')
    await page(`document.querySelector('.voz-choice__shape--${design}').closest('label').click()`)
    await waitFor(`document.documentElement.dataset.design === '${design}'`, 'el diseño ' + design)
    await click(header('Settings')) // cierra el menú
    await clickEmpty()
  }
  await setDesign('m3')
  await sleep(600)
  await shot('v-library-material3.png', windowUntil('.voz-library', 48))
  await setDesign('carbon')

  // --- gestor de modelos: la sección de transcripción (instalados, tamaños, licencias) ---
  await page(`location.hash = '#/modelos'`)
  await waitFor(`document.querySelector('.voz-models table')`, 'el gestor de modelos')
  await waitFor(`!document.querySelector('.voz-models [aria-busy="true"]')`, 'el gestor de modelos')
  await sleep(600)
  await shot('v-models.png', windowUntil('.voz-models table'))

  // --- añadir modelo por enlace: «Check link» solo lee metadatos; nunca se confirma ---
  await clickText('button', 'Add a custom model')
  await waitFor(`document.querySelector('.cds--modal.is-visible input[id$="-link"]')`, 'el dialogo de añadir modelo')
  await typeInto('.cds--modal.is-visible input[id$="-link"]', hfLink)
  await sleep(300)
  await clickText('button', 'Check link', `document.querySelector('.cds--modal.is-visible')`)
  try {
    await waitFor(
      `/Confirm and install/.test(document.querySelector('.cds--modal.is-visible')?.textContent ?? '') ||
        document.querySelector('.cds--modal.is-visible .cds--inline-notification--error')`,
      'el resultado de Check link',
      45000,
    )
  } catch {
    console.warn('aviso: Check link no respondio; la captura muestra el dialogo sin resultado')
  }
  await sleep(600)
  console.log('    check link: ' + (await page(`document.querySelector('.cds--modal.is-visible .cds--modal-content')?.innerText.replace(/\\n+/g, ' | ')`)))
  await shot('v-model-import-url.png', windowUntil('.voz-models table'))
  await clickText('button', 'Cancel', `document.querySelector('.cds--modal.is-visible')`)
  await sleep(400)

  // --- voz: modelo → idioma → voz, y una frase corta generada de verdad (CPU) ---
  await page(`location.hash = '#/speak'`)
  await waitFor(`document.querySelector('select[id$="-voice-select"]')`, 'la pantalla de voz')
  await choose('select[id$="-model"]', 'Kokoro')
  await sleep(300)
  await choose('select[id$="-language"]', 'English')
  await sleep(300)
  await choose('select[id$="-voice-select"]', 'af_heart')
  await typeInto('main textarea', 'Welcome to V. Your recordings, transcripts and voices stay on this computer.')
  const started = Date.now()
  await clickText('button', 'Generate audio')
  await waitFor(`document.querySelector('.voz-speak-result--completed')`, 'el audio generado', 120000)
  console.log(`ok  sintesis en ${((Date.now() - started) / 1000).toFixed(1)} s`)
  await clickEmpty()
  await viewport(1300)
  await shot('v-speech.png', windowUntil('.voz-speak-result', 16))
} finally {
  // matar `flatpak run` no cierra el Chrome del sandbox: se cierra por CDP
  await Promise.race([cdp.send('Browser.close').catch(() => undefined), sleep(2000)])
  cdp.close()
  chrome.child.kill()
}
