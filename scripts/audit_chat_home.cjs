const path = require('path')
const fs = require('fs')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE)

const baseUrl = process.env.AUDIT_BASE_URL || 'http://127.0.0.1:3000'
const outputDir = path.resolve(process.env.AUDIT_OUTPUT_DIR || 'logs/chat-home-audit')
const imageFile = path.resolve('eval/images/ai/ai_generated_breakfast_table_20260705.png')
const videoFile = path.resolve('data/ImageForTest/11 real.mp4')

fs.mkdirSync(outputDir, { recursive: true })

const result = {
  screenshots: [],
  consoleErrors: [],
  checks: {}
}

const capture = async (page, name, fullPage = false) => {
  const target = path.join(outputDir, name)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.evaluate(() => document.fonts?.ready)
  await page.waitForTimeout(500)
  await page.screenshot({ path: target, fullPage })
  result.screenshots.push(target)
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
    const desktop = await browser.newPage({ viewport: { width: 1440, height: 960 } })
    desktop.on('console', (message) => {
      if (message.type() === 'error') result.consoleErrors.push(`desktop: ${message.text()}`)
    })
    await enterAsGuest(desktop)
    await capture(desktop, '01-home-desktop.png')
    result.checks.homeTitle = await desktop.locator('#home-title').innerText()
    result.checks.chatPlaceholder = await desktop.getByRole('textbox', { name: '输入鉴伪需求' }).getAttribute('placeholder')
    result.checks.quickActions = await desktop.locator('.quick-actions button').count()

    const chatBox = desktop.getByRole('textbox', { name: '输入鉴伪需求' })
    await chatBox.fill('/')
    await desktop.locator('.command-palette').waitFor({ state: 'visible' })
    result.checks.commandSuggestions = await desktop.locator('.command-palette [role="option"]').count()
    await capture(desktop, '01b-command-palette-desktop.png')
    await chatBox.fill('请判断这张图片是否经过 AI 生成或编辑')
    const imageChooserPromise = desktop.waitForEvent('filechooser')
    await chatBox.press('Enter')
    const imageChooser = await imageChooserPromise
    await imageChooser.setFiles(imageFile)
    await desktop.locator('.analysis-workspace').waitFor({ state: 'visible' })
    await capture(desktop, '02-image-workbench-desktop.png')
    result.checks.imageAction = await desktop.getByRole('button', { name: '开始鉴伪' }).innerText()
    result.checks.imagePreview = await desktop.locator('.media-preview img').count()

    await desktop.getByRole('button', { name: '返回烛龙鉴伪主界面' }).click()
    await desktop.locator('#home-title').waitFor({ state: 'visible' })
    const videoChooserPromise = desktop.waitForEvent('filechooser')
    await desktop.getByRole('button', { name: /视频鉴伪/ }).last().click()
    const videoChooser = await videoChooserPromise
    await videoChooser.setFiles(videoFile)
    await desktop.locator('.media-preview video').waitFor({ state: 'visible' })
    await capture(desktop, '03-video-workbench-desktop.png')
    result.checks.videoHeading = await desktop.locator('#page-title').innerText()
    result.checks.videoPreview = await desktop.locator('.media-preview video').count()
    result.checks.videoDuration = await desktop.locator('.file-summary dd').nth(1).innerText()
    await desktop.close()

    const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
    mobile.on('console', (message) => {
      if (message.type() === 'error') result.consoleErrors.push(`mobile: ${message.text()}`)
    })
    await enterAsGuest(mobile)
    await capture(mobile, '04-home-mobile.png', true)
    result.checks.mobileScrollWidth = await mobile.evaluate(() => document.documentElement.scrollWidth)
    result.checks.mobileViewportWidth = await mobile.evaluate(() => window.innerWidth)
    await mobile.close()
  } finally {
    await browser.close()
  }

  process.stdout.write(JSON.stringify(result, null, 2))
}

run().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
