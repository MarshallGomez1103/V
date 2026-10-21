// V0-06: comprueba que, tras un seek y el autoscroll, el segmento activo tiene texto visible.
// Chrome headless por CDP (solo Node >= 22, sin dependencias).
// Los datos son sinteticos: `scripts/seed_segment_rows.py` los
// siembra en una base TEMPORAL (nunca en ~/.local/share/voz).
//
//   REPRO_URL=http://127.0.0.1:5199 REPRO_JOB=<id> REPRO_OUT=<dir> node scripts/repro-segment-rows.mjs
//   (REPRO_URL: Vite dev con VOZ_API apuntando a un VOZ de pruebas, o ese VOZ si ya lo sirve.)
import { spawn } from 'node:child_process'
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const env = (name, fallback) => {
  const value = process.env[name] ?? fallback
  if (!value) throw new Error('falta la variable ' + name)
  return value
}
const base = env('REPRO_URL')
const job = env('REPRO_JOB')
const out = env('REPRO_OUT', join(tmpdir(), 'repro-segment-rows'))
const chromePath = env(
  'CHROME_CMD',
  join(
    process.env.HOME ?? '',
    '.cache/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-linux64/chrome-headless-shell',
  ),
)
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
mkdirSync(out, { recursive: true })

const profile = mkdtempSync(join(tmpdir(), 'repro-chrome-'))
const port = 9300 + Math.floor(Math.random() * 500)
const child = spawn(
  chromePath,
  [
    '--no-sandbox',
    '--disable-gpu',
    '--hide-scrollbars',
    '--autoplay-policy=no-user-gesture-required',
    `--user-data-dir=${profile}`,
    `--remote-debugging-port=${port}`,
    '--window-size=1440,1000',
    'about:blank',
  ],
  { stdio: 'ignore' },
)

async function wsUrl() {
  for (let i = 0; i < 100; i += 1) {
    try {
      const pages = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).filter(
        (t) => t.type === 'page',
      )
      if (pages[0]) return pages[0].webSocketDebuggerUrl
    } catch {
      /* arrancando */
    }
    await sleep(200)
  }
  throw new Error('Chrome no abrio el puerto de depuracion')
}

const ws = new WebSocket(await wsUrl())
await new Promise((resolve, reject) => {
  ws.onopen = resolve
  ws.onerror = () => reject(new Error('fallo el WebSocket de CDP'))
})
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
const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const id = nextId++
    pending.set(id, { resolve, reject })
    ws.send(JSON.stringify({ id, method, params }))
  })
async function page(expression) {
  const { result, exceptionDetails } = await send('Runtime.evaluate', {
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
async function shot(name) {
  const { data } = await send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(join(out, name), Buffer.from(data, 'base64'))
}

// Estado de las filas pintadas respecto de la ventana de la lista.
const INSPECT = `(() => {
  const box = document.querySelector('.segments-scroll')
  const view = box.getBoundingClientRect()
  const rows = [...box.querySelectorAll('li[data-segment-index]')]
  const info = rows.map((row) => {
    const r = row.getBoundingClientRect()
    const text = row.querySelector('.segment-text')
    return {
      index: Number(row.dataset.segmentIndex),
      active: row.getAttribute('aria-current') === 'true',
      inView: r.bottom > view.top && r.top < view.bottom,
      height: Math.round(r.height),
      text: (text?.innerText ?? '').trim(),
      textHeight: text ? Math.round(text.getBoundingClientRect().height) : 0,
      cv: getComputedStyle(row).contentVisibility,
    }
  })
  const active = info.find((row) => row.active) ?? null
  return {
    scrollTop: Math.round(box.scrollTop),
    rendered: rows.length,
    active,
    blankInView: info.filter((row) => row.inView && (row.text === '' || row.textHeight === 0)),
    contentVisibility: [...new Set(info.map((row) => row.cv))],
  }
})()`

let failed = false
try {
  await send('Page.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
  await send('Page.navigate', { url: `${base}/#/t/${job}` })
  await waitFor(`document.querySelectorAll('.segments li').length > 0`, 'las filas de segmentos')
  await waitFor(`document.querySelector('audio') && document.querySelector('audio').duration > 0`, 'el audio', 30000)
  const duration = await page(`document.querySelector('audio').duration`)
  console.log(`audio ${duration.toFixed(0)} s`)

  for (const [name, fraction] of [['50', 0.5], ['90', 0.9], ['25', 0.25], ['2', 0.02], ['75', 0.75]]) {
    // seek como lo haria el usuario: el reproductor emite timeupdate/seeked y la lista sigue
    await page(`(() => { const a = document.querySelector('audio'); a.currentTime = a.duration * ${fraction} })()`)
    await sleep(Number(process.env.REPRO_SETTLE ?? 1200)) // autoscroll (far => behavior auto) + medicion de filas + re-render
    const state = await page(INSPECT)
    await shot(`seek-${name}.png`)
    const active = state.active
    const ok =
      active !== null && active.inView && active.text.length > 0 && active.textHeight > 0 && state.blankInView.length === 0
    failed ||= !ok
    console.log(`${ok ? 'ok  ' : 'FALLA'} seek ${name}%: ` + JSON.stringify({ ...state, active }))
  }
} finally {
  await Promise.race([send('Browser.close').catch(() => undefined), sleep(2000)])
  ws.close()
  child.kill()
}
process.exit(failed ? 1 : 0)
