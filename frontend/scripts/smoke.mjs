// End-to-end smoke test against a running app (API + web).
//   npm run smoke
import { BASE_URL, generateFrom, launch } from './browser.mjs'

const browser = await launch()
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true })
const page = await context.newPage()
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
let failed = 0
const check = (cond, msg) => {
  console.log(`${cond ? 'pass' : 'FAIL'}  ${msg}`)
  if (!cond) failed++
}
const planRooms = (p, type) => p.locator(`.canvas-stage [data-type="${type}"]`).count()

await page.goto(BASE_URL)
await page.waitForSelector('.variant', { timeout: 30000 })
check((await page.locator('.variant').count()) >= 2, 'first visit generates variants')

await generateFrom(page, '2 bedroom apartment, 800 sqft')
await page.click('.disclosure summary')
await page.click('button[aria-label="Increase Bedroom"]')
check(await page.locator('.badge', { hasText: 'edited' }).isVisible(), 'program edits are flagged')
await page.click('.btn-primary')
await page.waitForSelector('.canvas-busy', { state: 'detached' }).catch(() => {})
await page.waitForTimeout(300)
check((await planRooms(page, 'bedroom')) === 3, 'edited program is generated')
const hash = await page.evaluate(() => location.hash)
check(hash.startsWith('#b='), 'share link is written to the URL')

const before = await page.locator('.variant.is-selected .variant-name').innerText()
await page.keyboard.press('ArrowRight')
check((await page.locator('.variant.is-selected .variant-name').innerText()) !== before, 'arrow keys switch variants')

const vb = await page.getAttribute('.canvas-stage svg', 'viewBox')
await page.mouse.move(700, 400)
await page.mouse.wheel(0, -400)
await page.waitForTimeout(150)
check((await page.getAttribute('.canvas-stage svg', 'viewBox')) !== vb, 'wheel zooms the plan')

await page.click('.canvas-stage [data-type="bedroom"] >> nth=0', { force: true })
check(await page.locator('.inspector').isVisible(), 'clicking a room opens the inspector')
await page.keyboard.press('Escape')
check(!(await page.locator('.inspector').isVisible()), 'Esc closes the inspector')

await page.click('#tab-export')
const [download] = await Promise.all([page.waitForEvent('download'), page.click('.format >> nth=0')])
check(download.suggestedFilename().endsWith('.pdf'), 'PDF export downloads')

const shared = await context.newPage()
await shared.goto(BASE_URL + hash)
await shared.waitForSelector('.variant', { timeout: 30000 })
check((await planRooms(shared, 'bedroom')) === 3, 'share link reproduces the plan')

check(errors.length === 0, `no console errors${errors.length ? ': ' + errors.join(' | ') : ''}`)
await browser.close()
process.exit(failed ? 1 : 0)
