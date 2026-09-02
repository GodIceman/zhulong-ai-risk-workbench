const path = require('path')
const fs = require('fs')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE)

const baseUrl = process.env.AUDIT_BASE_URL || 'http://127.0.0.1:3000'
const outputDir = path.resolve(process.env.AUDIT_OUTPUT_DIR || 'logs/glass-module-audit')
const sampleFile = path.resolve('eval/images/ai/ai_generated_breakfast_table_20260705.png')
const desktopViewport = {
  width: Number(process.env.AUDIT_DESKTOP_WIDTH || 1440),
  height: Number(process.env.AUDIT_DESKTOP_HEIGHT || 960)
}

fs.mkdirSync(outputDir, { recursive: true })

const result = { screenshots: [], consoleErrors: [], checks: {} }

const capture = async (page, name, fullPage = false) => {
  if (process.env.AUDIT_REDUCED_MOTION !== 'false') {
    await page.emulateMedia({ reducedMotion: 'reduce' })
  }
  await page.evaluate(() => document.fonts?.ready)
  await page.waitForTimeout(450)
  const target = path.join(outputDir, name)
  await page.screenshot({ path: target, fullPage })
  result.screenshots.push(target)
}

const mockReport = {
  task_id: 'TASK-GLASS-MODULE-QA',
  media_type: 'image',
  verdict: 'ai_generated',
  risk_level: 'high',
  confidence: 0.91,
  summary: '多项模型信号表明该图片存在较高的 AI 生成风险，建议结合原始来源进行人工复核。',
  evidence: [
    {
      id: 'ai-image-score',
      title: '主模型检测到明显生成信号',
      description: '纹理一致性与局部结构呈现出生成式模型常见特征。',
      severity: 'high',
      confidence: 0.91,
      model_score: 0.91,
      signals: ['局部纹理一致性异常', '细节结构重复']
    },
    {
      id: 'metadata-source',
      title: '缺少可信原始来源',
      description: '文件中未读取到可验证的相机与内容凭证信息。',
      severity: 'medium',
      confidence: 0.72,
      signals: ['无相机 EXIF', '无内容凭证']
    }
  ],
  visualization: {},
  metadata: {
    filename: 'ai_generated_breakfast_table_20260705.png',
    file_size_label: '2.1 MB',
    format: 'png',
    width: 1448,
    height: 1086,
    resolution: '1448 × 1086',
    source_hint: 'auto',
    exif_present: false
  },
  models: [
    { model_id: 'ai-image-detector', model_version: 'qa', ai_score: 0.91, score: 0.91 }
  ],
  decision: {
    evidence_scores: {
      ai_evidence_strength: 0.91,
      real_evidence_strength: 0.18,
      provenance_strength: 0.12,
      conflict_level: 'low'
    }
  },
  limitations: ['检测结果仅作为辅助判断，不构成司法鉴定结论。'],
  created_at: new Date().toISOString()
}

const installApiMocks = async (page) => {
  const handler = async (route) => {
    const url = new URL(route.request().url())
    let body
    if (url.pathname === '/api/media/analyze') {
      body = { success: true, task_id: mockReport.task_id, status: 'received' }
    } else if (url.pathname.endsWith('/report')) {
      body = { success: true, report: mockReport }
    } else {
      body = {
        success: true,
        task_id: mockReport.task_id,
        status: 'completed',
        progress: 100,
        message: '检测完成'
      }
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  }

  await page.route('http://localhost:5002/**', handler)
  await page.route('http://127.0.0.1:5002/**', handler)
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
    const desktop = await browser.newPage({ viewport: desktopViewport })
    desktop.on('console', (message) => {
      if (message.type() === 'error') result.consoleErrors.push(`desktop: ${message.text()}`)
    })
    await installApiMocks(desktop)
    await desktop.goto(baseUrl, { waitUntil: 'networkidle' })
    await capture(desktop, '01-login-glass-desktop.png')
    result.checks.loginCard = await desktop.locator('.login-card').evaluate((element) => {
      const style = getComputedStyle(element)
      return { borderRadius: style.borderRadius, backdropFilter: style.backdropFilter, background: style.backgroundColor }
    })

    await desktop.getByRole('button', { name: '游客登录' }).click()
    await desktop.waitForURL(/dashboard/, { timeout: 10000 })
    await desktop.locator('input[type="file"]').setInputFiles(sampleFile)
    await desktop.getByRole('button', { name: '开始鉴伪' }).click()
    await desktop.locator('.result-workspace').waitFor({ state: 'visible', timeout: 10000 })
    await capture(desktop, '02-report-glass-desktop.png', true)
    result.checks.reportModules = await desktop.locator('.content-section').count()
    result.checks.reportStyle = await desktop.locator('.report').evaluate((element) => {
      const style = getComputedStyle(element)
      return { borderRadius: style.borderRadius, backdropFilter: style.backdropFilter }
    })
    await desktop.close()

    const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
    mobile.on('console', (message) => {
      if (message.type() === 'error') result.consoleErrors.push(`mobile: ${message.text()}`)
    })
    await installApiMocks(mobile)
    await mobile.goto(baseUrl, { waitUntil: 'networkidle' })
    await capture(mobile, '03-login-glass-mobile.png', true)
    await enterAsGuest(mobile)
    await mobile.locator('input[type="file"]').setInputFiles(sampleFile)
    await mobile.getByRole('button', { name: '开始鉴伪' }).click()
    await mobile.locator('.result-workspace').waitFor({ state: 'visible', timeout: 10000 })
    await capture(mobile, '04-report-glass-mobile.png', true)
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
