// S16.02: maneja la UI real de VOZ con Chrome headless por CDP y guarda capturas PNG.
// Lo lanza scripts/capture-screenshots.sh (servidor, datos y XDG temporales).
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
const audioPath = env('CAPTURE_AUDIO')
const outDir = env('CAPTURE_OUT')
const profile = env('CAPTURE_PROFILE')
const model = env('CAPTURE_MODEL')
const haveModel = process.env.CAPTURE_HAVE_MODEL === '1'
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
    '--lang=es',
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

// guarda un PNG. Sin selector: solo la ventana visible. Con selector: recorta a ese
// elemento (y hasta `through` si se da). `live` hace scroll y no captura fuera de la
// ventana: las filas de segmentos usan content-visibility:auto y solo se pintan a la vista.
async function shot(name, selector, { pad = 16, live = false, through = selector } = {}) {
  const params = { format: 'png', captureBeyondViewport: Boolean(selector) }
  if (selector) {
    const box = await page(`(() => {
      const a = document.querySelector(${JSON.stringify(selector)})
      const b = document.querySelector(${JSON.stringify(through)})
      if (!a || !b) return null
      if (${live}) scrollTo(0, a.getBoundingClientRect().top + scrollY - ${pad})
      const r = a.getBoundingClientRect()
      const e = b.getBoundingClientRect()
      const o = [scrollX, scrollY]
      return { x: r.left + o[0], y: r.top + o[1], w: r.width, h: e.bottom - r.top }
    })()`)
    if (!box) throw new Error('no existe ' + selector + ' o ' + through)
    if (live) await sleep(300)
    const x = Math.max(0, box.x - pad)
    const y = Math.max(0, box.y - pad)
    params.clip = { x, y, width: Math.min(WIDTH - x, box.w + pad * 2), height: box.h + pad * 2, scale: 1 }
  }
  const { data } = await cdp.send('Page.captureScreenshot', params)
  const file = join(outDir, name)
  const bytes = Buffer.from(data, 'base64')
  writeFileSync(file, bytes)
  console.log(`ok  ${name} (${Math.round(bytes.length / 1024)} KB)`)
}

const click = (selector) =>
  page(`document.querySelector(${JSON.stringify(selector)}).click()`)

try {
  await cdp.send('Page.enable')
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width: WIDTH,
    height: HEIGHT,
    deviceScaleFactor: 1,
    mobile: false,
  })
  await cdp.send('Page.navigate', { url })
  await waitFor(`document.querySelector('h1') && document.querySelector('.model-manager')`, 'la pagina de inicio')
  await waitFor(`!document.querySelector('.model-manager [aria-busy="true"]')`, 'el gestor de modelos')
  await sleep(500)
  await shot('01-inicio.png')

  // importar el audio de demo: se inyecta como un File real en el input de la tarjeta
  const audioB64 = readFileSync(audioPath).toString('base64')
  await page(`(async () => {
    const bytes = Uint8Array.from(atob(${JSON.stringify(audioB64)}), (c) => c.charCodeAt(0))
    const file = new File([bytes], 'reunion-demo.wav', { type: 'audio/wav' })
    const transfer = new DataTransfer()
    transfer.items.add(file)
    const input = document.querySelector('input[type=file]')
    input.files = transfer.files
    input.dispatchEvent(new Event('change', { bubbles: true }))
  })()`)
  await waitFor(`document.querySelector('.import-submit:not([disabled])')`, 'el archivo listo')
  await page(`(() => {
    const input = document.querySelector('#main input[type=text]')
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
    set.call(input, 'Reunión de proyecto (demo)')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })()`)
  await click('.import-submit')
  await waitFor(`document.querySelector('.import-summary')`, 'la importacion')
  await waitFor(`document.querySelector('.options-card .options-list')`, 'las opciones de motor')
  await sleep(600)

  // selector de motor: elegir el modelo de la demo si esta disponible
  if (haveModel) {
    const chosen = await page(`(() => {
      const wanted = ${JSON.stringify(model)}.toLowerCase()
      for (const li of document.querySelectorAll('.options-list li')) {
        const radio = li.querySelector('input[type=radio]')
        if (radio && !radio.disabled && li.textContent.toLowerCase().includes(wanted)) {
          radio.click()
          return true
        }
      }
      return false
    })()`)
    if (!chosen) throw new Error('la opcion de motor ' + model + ' no esta disponible para iniciar')
    await sleep(300)
  }
  await shot('02-selector-motor.png', '.options-card')

  if (haveModel) {
    // capturar el job en curso (opcional: con GPU puede terminar antes de verlo) y el terminado
    await click('.options-card .import-submit')
    await waitFor(`document.querySelector('.job-card')`, 'el job')
    const limit = Date.now() + 120000
    let savedRunning = false
    while (Date.now() < limit) {
      const state = await page(`(() => {
        const card = document.querySelector('.job-card')
        return card ? [...card.classList].find((c) => c.startsWith('job-card--')) ?? '' : ''
      })()`)
      if (!savedRunning && /transcribing|preprocessing|probing|queued|aligning/.test(state)) {
        await shot('03-job-en-curso.png', '.job-card')
        savedRunning = true
      }
      if (/completed|failed|cancelled/.test(state)) break
      await sleep(50)
    }
    await waitFor(`document.querySelector('.job-card--completed')`, 'el job completado', 5000)
    await waitFor(`document.querySelectorAll('.segments li').length > 0`, 'los segmentos')
    await sleep(800)
    console.log('palabras con timing en la UI: ' + (await page(`document.querySelectorAll('.segments .word').length`)))
    await shot('04-job-terminado.png', '.job-card')
    // la transcripcion: barra de modo/exportacion + segmentos con palabras
    await shot('05-forma-de-onda.png', '.audio-card')
    await shot('06-transcripcion.png', '.transcript-tools', { live: true, through: '.segments-card' })
  }

  // gestor de modelos (con el modelo importado si lo hubo)
  await sleep(300)
  await shot('07-gestor-modelos.png', '.model-manager')
} finally {
  // matar `flatpak run` no cierra el Chrome del sandbox: se cierra por CDP
  await Promise.race([cdp.send('Browser.close').catch(() => undefined), sleep(2000)])
  cdp.close()
  chrome.child.kill()
}
