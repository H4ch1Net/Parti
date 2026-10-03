// Captures the README screenshots into docs/screenshots.
// Needs the API and the web app running (see README "Development").
//   npm run screenshots
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { BASE_URL, generateFrom, launch } from './browser.mjs'

const OUT = resolve(dirname(fileURLToPath(import.meta.url)), '../../docs/screenshots')
await mkdir(OUT, { recursive: true })

const browser = await launch()

async function shot(name, { width = 1440, height = 900, scheme = 'light', prompt, setup } = {}) {
  const page = await browser.newPage({ viewport: { width, height }, colorScheme: scheme, deviceScaleFactor: 2 })
  await page.goto(BASE_URL)
  await page.waitForSelector('.variant', { timeout: 30000 })
  if (prompt) await generateFrom(page, prompt)
  if (setup) await setup(page)
  await page.waitForTimeout(300)
  await page.screenshot({ path: `${OUT}/${name}.png` })
  await page.close()
  console.log(`wrote docs/screenshots/${name}.png`)
}

await shot('workspace', { prompt: '3 bed 2 bath house, 1,300 sq ft, open plan with a dining area' })
await shot('inspector-dark', {
  scheme: 'dark',
  prompt: 'Three bedroom home with a home office, laundry and a 2-car garage, 1,650 sq ft',
  setup: async (page) => {
    await page.click('.canvas-stage [data-room="bedroom_1"]', { force: true })
    await page.click('#tab-rooms')
  },
})
await shot('two-levels', {
  prompt: 'Two story house, 1800 sqft, 3 bedrooms upstairs, living, kitchen and dining downstairs',
  setup: async (page) => {
    await page.keyboard.press('2')
    await page.click('#tab-checks')
  },
})
await shot('program-editor', {
  prompt: 'Small office, 600 sqft: reception, 3 private offices and a restroom',
  setup: async (page) => {
    await page.click('.disclosure summary')
    await page.keyboard.press('u')
  },
})
await shot('mobile', { width: 390, height: 844, prompt: 'Studio apartment, 400 sq ft, with a full bathroom' })

// A raw PDF/PNG-style drawing straight from the export endpoint.
const api = BASE_URL.replace(/\/$/, '')
const gen = await fetch(`${api}/api/generate`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ prompt: '4 bedroom 2.5 bathroom house, 2000 sqft, master ensuite', count: 1 }),
}).then((r) => r.json())
const png = await fetch(`${api}/api/export/png`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ candidate: gen.candidates[0], units: 'metric' }),
})
await writeFile(`${OUT}/export-drawing.png`, Buffer.from(await png.arrayBuffer()))
console.log('wrote docs/screenshots/export-drawing.png')

await browser.close()
