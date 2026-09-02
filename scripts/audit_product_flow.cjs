const path = require('path')
const fs = require('fs')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE)

const baseUrl = process.env.AUDIT_BASE_URL || 'http://127.0.0.1:5173'
const outputDir = path.resolve(process.env.AUDIT_OUTPUT_DIR || 'logs/product-audit-current')
const sampleFile = path.resolve(process.env.AUDIT_SAMPLE_FILE || 'eval/images/ai/ai_generated_breakfast_table_20260705.png')

fs.mkdirSync(outputDir, { recursive: true })

const findings = {
  baseUrl,
  outputDir,
  sampleFile,
  screenshots: [],
  consoleErrors: [],
  desktop: {},
  mobile: {}
}

const stablePage = async (page) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.evaluate(() => document.fonts?.ready)
  await page.waitForTimeout(250)
}

const capture = async (page, name, fullPage = false) => {
  const target = path.join(outputDir, name)
  await stablePage(page)
  await page.screenshot({ path: target, fullPage })
  findings.screenshots.push(target)
}

const enterAsGuest = async (page) => {
  await page.goto(baseUrl, { waitUntil: 'networkidle' })
  if (page.url().includes('/login')) {
    await page.getByRole('button', { name: '游客登录' }).click()
    await page.waitForURL(/dashboard/, { timeout: 10000 })
  }
  await page.waitForLoadState('networkidle')
}

const run = async () => {
const browser = await chromium.launch({ headless: true })

try {
  const desktopContext = await browser.newContext({
    viewport: { width: 1440, height: 960 },
    deviceScaleFactor: 1,
    colorScheme: 'dark'
  })
  const desktop = await desktopContext.newPage()
  desktop.on('console', (message) => {
    if (message.type() === 'error') findings.consoleErrors.push(`desktop: ${message.text()}`)
  })

  await desktop.goto(baseUrl, { waitUntil: 'networkidle' })
  await capture(desktop, '01-login-desktop.png')
  findings.desktop.loginTitle = await desktop.locator('h1').first().textContent()
  await desktop.getByRole('button', { name: '游客登录' }).click()
  await desktop.waitForURL(/dashboard/, { timeout: 10000 })
  await capture(desktop, '02-dashboard-empty-desktop.png')

  const desktopInput = desktop.locator('input[type="file"]')
  await desktopInput.setInputFiles({
    name: 'oversized.png',
    mimeType: 'image/png',
    buffer: Buffer.alloc(20 * 1024 * 1024 + 1)
  })
  findings.desktop.oversizeError = await desktop.locator('.error-message').textContent()
  await desktopInput.setInputFiles(sampleFile)
  await capture(desktop, '03-file-selected-desktop.png')
  findings.desktop.primaryAction = await desktop.getByRole('button', { name: '开始检测' }).textContent()
  findings.desktop.uploadCopy = await desktop.locator('.dropzone').innerText()

  await desktop.getByRole('button', { name: '开始检测' }).click()
  await desktop.waitForTimeout(120)
  await capture(desktop, '04-detecting-desktop.png')
  await desktop.locator('.result-workspace').waitFor({ state: 'visible', timeout: 30000 })
  await capture(desktop, '05-result-desktop.png')
  findings.desktop.resultHeading = await desktop.locator('.result-overview h2').textContent()
  findings.desktop.resultText = await desktop.locator('.result-workspace').innerText()
  findings.desktop.technicalDetailsCollapsed = !(await desktop.locator('.technical-details').getAttribute('open'))

  await desktop.getByRole('button', { name: '历史记录' }).click()
  await capture(desktop, '06-history-desktop.png')
  findings.desktop.historyText = await desktop.locator('.history-panel').innerText()
  await desktopContext.close()

  const mobileContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 1,
    colorScheme: 'dark',
    isMobile: true,
    hasTouch: true
  })
  const mobile = await mobileContext.newPage()
  mobile.on('console', (message) => {
    if (message.type() === 'error') findings.consoleErrors.push(`mobile: ${message.text()}`)
  })

  await enterAsGuest(mobile)
  await capture(mobile, '07-dashboard-empty-mobile.png')
  await mobile.locator('input[type="file"]').setInputFiles(sampleFile)
  await capture(mobile, '08-file-selected-mobile.png')
  await mobile.getByRole('button', { name: '开始检测' }).click()
  await mobile.locator('.result-workspace').waitFor({ state: 'visible', timeout: 30000 })
  await capture(mobile, '09-result-mobile.png')

  findings.mobile.bodyScrollWidth = await mobile.evaluate(() => document.body.scrollWidth)
  findings.mobile.viewportWidth = await mobile.evaluate(() => window.innerWidth)
  findings.mobile.resultLayout = await mobile.locator('.report').evaluate((element) => ({
    scrollHeight: element.scrollHeight,
    clientHeight: element.clientHeight,
    scrollWidth: element.scrollWidth,
    clientWidth: element.clientWidth
  }))
  await mobile.locator('.dashboard').evaluate((element) => { element.scrollTop = 1400 })
  await capture(mobile, '10-result-mobile-scrolled.png')
  findings.mobile.inlineResult = await mobile.locator('.report-overlay').count() === 0
  await mobileContext.close()
} finally {
  await browser.close()
}

process.stdout.write(JSON.stringify(findings, null, 2))
}

run().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
