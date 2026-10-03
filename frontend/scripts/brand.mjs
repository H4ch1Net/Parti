// Renders the brand images from the design tokens and a real plan:
//   docs/brand/banner.png, public/og-image.png, public/apple-touch-icon.png
// Needs the API running (see README "Development").
//   npm run brand
import { mkdir, readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { launch } from './browser.mjs'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const API = process.env.PARTI_API ?? 'http://localhost:8000'

const css = (await Promise.all(['src/styles/tokens.css', 'src/styles/plan.css'].map((p) => readFile(resolve(ROOT, p), 'utf8')))).join('\n')
const font = (await readFile(resolve(ROOT, 'node_modules/@fontsource-variable/archivo/files/archivo-latin-wdth-normal.woff2'))).toString('base64')

const gen = await fetch(`${API}/api/generate`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ prompt: '3 bed 2 bath house, 1,300 sq ft, open plan with a dining area', count: 1 }),
}).then((r) => r.json())
const plan = gen.drawings[gen.candidates[0].id][0]

const MARK = `<svg class="mark" viewBox="0 0 32 32" aria-hidden="true">
  <rect x="4.5" y="4.5" width="23" height="23" fill="var(--sheet)" stroke="var(--ink)" stroke-width="2.5"/>
  <path d="M4.5 18.5h23M14 4.5v14M20.5 18.5v9" stroke="var(--ink)" stroke-width="1.6" fill="none"/>
  <rect x="16.4" y="7" width="8.6" height="9" fill="var(--accent)"/></svg>`

// Same patterns as components/PlanPatterns.tsx.
const PATTERNS = `<svg width="0" height="0" style="position:absolute"><defs>
  <pattern id="zp-public" width="0.3" height="0.3" patternUnits="userSpaceOnUse"><rect width="0.3" height="0.3" style="fill:var(--zone-public)"/><circle cx="0.15" cy="0.15" r="0.018" style="fill:var(--hatch)"/></pattern>
  <pattern id="zp-private" width="0.3" height="0.3" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="0.3" height="0.3" style="fill:var(--zone-private)"/><path d="M0 0.15H0.3" style="stroke:var(--hatch);stroke-width:0.016"/></pattern>
  <pattern id="zp-service" width="0.3" height="0.3" patternUnits="userSpaceOnUse"><rect width="0.3" height="0.3" style="fill:var(--zone-service)"/><path d="M0 0.15H0.3M0.15 0V0.3" style="stroke:var(--hatch);stroke-width:0.012"/></pattern>
</defs></svg>`

const BASE_CSS = `
@font-face { font-family: 'Archivo Variable'; src: url(data:font/woff2;base64,${font}) format('woff2'); font-weight: 100 900; font-stretch: 62% 125%; }
${css}
* { box-sizing: border-box; margin: 0; }
body { background: var(--desk); color: var(--ink); font-family: var(--font); -webkit-font-smoothing: antialiased; }
.desk { position: relative; width: 100vw; height: 100vh; padding: var(--pad);
  background:
    repeating-linear-gradient(90deg, var(--rule-strong) 0 1px, transparent 1px 12.5%) top / 100% calc(var(--pad) * 0.6) no-repeat,
    repeating-linear-gradient(90deg, var(--rule-strong) 0 1px, transparent 1px 12.5%) bottom / 100% calc(var(--pad) * 0.6) no-repeat,
    var(--desk); }
.sheet { position: relative; display: grid; height: 100%; background: var(--sheet); border: 2px solid var(--frame); }
.wordmark { font-weight: 800; font-stretch: 125%; letter-spacing: -0.015em; line-height: 0.9; }
.caps { font-weight: 650; font-stretch: 86%; letter-spacing: 0.1em; text-transform: uppercase; }
.plan { position: relative; min-width: 0; min-height: 0; background-color: var(--canvas);
  background-image: radial-gradient(circle, var(--dot) 1px, transparent 1.4px); background-size: 20px 20px; }
.plan svg.pt-plan { position: absolute; inset: 6%; width: 88%; height: 88%; }
.crop { position: absolute; width: 18px; height: 18px; border: 0 solid var(--ink-3); }
.crop.tl { top: 12px; left: 12px; border-top-width: 1px; border-left-width: 1px; }
.crop.tr { top: 12px; right: 12px; border-top-width: 1px; border-right-width: 1px; }
.crop.bl { bottom: 12px; left: 12px; border-bottom-width: 1px; border-left-width: 1px; }
.crop.br { bottom: 12px; right: 12px; border-bottom-width: 1px; border-right-width: 1px; }
.tb { display: grid; grid-template-columns: repeat(3, 1fr); border: 1.5px solid var(--frame); }
.tb div { padding: 10px 14px 12px; }
.tb div + div { border-left: 1px solid var(--rule-strong); }
.tb dt { font-size: 11px; color: var(--ink-3); }
.tb dd { margin-top: 4px; font-size: 16px; font-weight: 600; white-space: nowrap; }
`

const crops = '<span class="crop tl"></span><span class="crop tr"></span><span class="crop bl"></span><span class="crop br"></span>'

function page(body, extra) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>${BASE_CSS}${extra}</style></head><body>${PATTERNS}${body}</body></html>`
}

const lockup = (tag) => `
  <div class="lockup">${MARK}<span class="wordmark">Parti</span></div>
  <p class="tag caps">${tag}</p>`

const banner = page(
  `<div class="desk units-metric"><div class="sheet">
    <div class="left">
      <div>${lockup('Schematic floor plans from a written brief')}</div>
      <dl class="tb">
        <div><dt class="caps">Input</dt><dd>A written brief</dd></div>
        <div><dt class="caps">Output</dt><dd>Six scored plans</dd></div>
        <div><dt class="caps">Export</dt><dd>PDF · SVG · PNG · DXF</dd></div>
      </dl>
    </div>
    <div class="plan">${plan}${crops}</div>
  </div></div>`,
  `.desk { --pad: 18px; }
   .sheet { grid-template-columns: 640px 1fr; }
   .left { display: flex; flex-direction: column; justify-content: space-between; padding: 44px 44px 40px; border-right: 1px solid var(--rule-strong); }
   .lockup { display: flex; align-items: center; gap: 22px; }
   .lockup .mark { width: 96px; height: 96px; }
   .lockup .wordmark { font-size: 120px; }
   .tag { margin-top: 26px; font-size: 17px; color: var(--ink-2); }`,
)

const og = page(
  `<div class="desk units-metric"><div class="sheet">
    <div class="left">${lockup('Schematic floor plans<br>from a written brief')}</div>
    <div class="plan">${plan}${crops}</div>
  </div></div>`,
  `.desk { --pad: 16px; }
   .sheet { grid-template-rows: auto 1fr; }
   .left { display: flex; align-items: center; justify-content: space-between; padding: 26px 34px; border-bottom: 1px solid var(--rule-strong); }
   .lockup { display: flex; align-items: center; gap: 16px; }
   .lockup .mark { width: 64px; height: 64px; }
   .lockup .wordmark { font-size: 76px; }
   .tag { font-size: 16px; line-height: 1.35; text-align: right; color: var(--ink-2); }`,
)

const icon = page(
  `<div class="icon">${MARK}</div>`,
  `body { background: var(--sheet); } .icon { display: grid; place-items: center; width: 100vw; height: 100vh; } .icon .mark { width: 150px; height: 150px; }`,
)

const browser = await launch()
async function render(html, out, width, height, scale) {
  const p = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: scale, colorScheme: 'light' })
  await p.setContent(html, { waitUntil: 'load' })
  await p.evaluate(() => document.fonts.ready)
  await mkdir(dirname(out), { recursive: true })
  await p.screenshot({ path: out })
  await p.close()
  console.log(`wrote ${out.replace(resolve(ROOT, '..') + '/', '')}`)
}

await render(banner, resolve(ROOT, '../docs/brand/banner.png'), 1600, 560, 1.5)
await render(og, resolve(ROOT, 'public/og-image.png'), 1200, 630, 1)
await render(icon, resolve(ROOT, 'public/apple-touch-icon.png'), 180, 180, 1)
await browser.close()
