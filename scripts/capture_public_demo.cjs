const fs = require('fs')
const path = require('path')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE)

const repoRoot = path.resolve(__dirname, '..')
const baseUrl = process.env.DEMO_BASE_URL || 'http://127.0.0.1:4173/zhulong-ai-risk-workbench/'
const outputDir = path.resolve(process.env.DEMO_OUTPUT_DIR || path.join(repoRoot, 'docs', 'assets'))
const sampleFile = path.resolve(
  process.env.DEMO_SAMPLE_FILE || path.join(repoRoot, 'zhulong', 'public', 'ruixen-moon-bg.png')
)

fs.mkdirSync(outputDir, { recursive: true })

const run = async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.BROWSER_EXECUTABLE
  })

  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 960 },
      deviceScaleFactor: 1,
      colorScheme: 'dark',
      reducedMotion: 'reduce'
    })
    const page = await context.newPage()
    const consoleErrors = []
    const failedResponses = []
    const failedRequests = []
    page.on('console', (message) => {
      if (message.type() === 'error') {
        consoleErrors.push({ text: message.text(), location: message.location() })
      }
    })
    page.on('response', (response) => {
      if (response.status() >= 400) {
        failedResponses.push({ status: response.status(), url: response.url() })
      }
    })
    page.on('requestfailed', (request) => {
      failedRequests.push({
        url: request.url(),
        error: request.failure()?.errorText || 'unknown'
      })
    })

    await page.goto(baseUrl, { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: '游客登录' }).click()
    await page.waitForURL(/dashboard/)
    await page.waitForLoadState('networkidle')
    await page.screenshot({
      path: path.join(outputDir, 'overview-desktop.png'),
      fullPage: true
    })

    await page.locator('input[type="file"]').setInputFiles(sampleFile)
    await page.getByRole('button', { name: '开始风险筛查' }).click()
    await page.locator('.result-workspace').waitFor({ state: 'visible', timeout: 15000 })
    await page.screenshot({
      path: path.join(outputDir, 'report-desktop.png'),
      fullPage: true
    })

    process.stdout.write(JSON.stringify({
      baseUrl,
      outputDir,
      sampleFile,
      consoleErrors,
      failedResponses,
      failedRequests
    }, null, 2))
  } finally {
    await browser.close()
  }
}

run().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
