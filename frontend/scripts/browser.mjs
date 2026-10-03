// Shared Playwright launcher for the screenshot and smoke scripts.
// Set CHROMIUM_PATH to use a system Chromium instead of Playwright's download.
import { chromium } from 'playwright'

export const BASE_URL = process.env.PARTI_URL ?? 'http://localhost:5173/'

export function launch() {
  return chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ['--no-sandbox'],
  })
}

export async function generateFrom(page, prompt) {
  await page.fill('textarea', prompt)
  await page.waitForTimeout(600)
  await page.keyboard.press('Control+Enter')
  await page.waitForSelector('.canvas-busy', { state: 'detached', timeout: 30000 }).catch(() => {})
  await page.waitForSelector('.variant')
  await page.waitForTimeout(500)
}
