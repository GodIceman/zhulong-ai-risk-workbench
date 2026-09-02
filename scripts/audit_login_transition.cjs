const fs = require('fs')
const path = require('path')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE)

const baseUrl = process.env.AUDIT_BASE_URL || 'http://127.0.0.1:3000'
const outputDir = path.resolve(process.env.AUDIT_OUTPUT_DIR || 'logs/login-transition-audit')

fs.mkdirSync(outputDir, { recursive: true })

const run = async () => {
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } })
  const consoleErrors = []

  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })

  try {
    await page.goto(`${baseUrl}/#/login`, { waitUntil: 'networkidle' })
    await page.locator('.form-input').first().click()
    await page.waitForTimeout(50)
    const loginChecks = await page.evaluate(() => {
      const brand = document.querySelector('.brand-name')
      const rect = brand?.getBoundingClientRect()
      const input = document.querySelector('.form-input')
      const inputStyle = input ? getComputedStyle(input) : null
      const passwordToggle = document.querySelector('.password-toggle')
      const passwordToggleStyle = passwordToggle ? getComputedStyle(passwordToggle) : null
      const loginButton = document.querySelector('.login-btn')
      const loginButtonStyle = loginButton ? getComputedStyle(loginButton) : null
      const registerLink = document.querySelector('.link-btn')
      const registerLinkStyle = registerLink ? getComputedStyle(registerLink) : null

      return {
        dragonEyeRemoved: !document.querySelector('.dragon-eye-frame, .dragon-eye'),
        brandWordmarkCentered: Boolean(rect && Math.abs(rect.left + rect.width / 2 - window.innerWidth / 2) < 1),
        brandWordmarkVisible: Boolean(rect && rect.width > 0 && rect.height > 0),
        inputFocusHighlightRemoved: Boolean(
          inputStyle &&
          inputStyle.borderColor === 'rgba(175, 224, 234, 0.15)' &&
          !inputStyle.boxShadow.includes('247, 215, 126') &&
          !inputStyle.boxShadow.includes('31, 151, 178')
        ),
        passwordToggleUsesLucideEye: Boolean(document.querySelector('.password-toggle .lucide-eye')),
        customPasswordEyeRemoved: !document.querySelector('.toggle-eye-outline, .toggle-eye-pupil, .toggle-eye-slash'),
        passwordToggleHasNoChrome: Boolean(
          passwordToggleStyle &&
          passwordToggleStyle.borderStyle === 'none' &&
          passwordToggleStyle.backgroundColor === 'rgba(0, 0, 0, 0)'
        ),
        loginButtonUsesTechBlue: Boolean(
          loginButtonStyle &&
          loginButtonStyle.backgroundImage.includes('linear-gradient') &&
          loginButtonStyle.backgroundImage.includes('67, 143, 198')
        ),
        registerLinkUsesTechBlue: registerLinkStyle?.color === 'rgb(98, 169, 216)'
      }
    })

    const loginButton = page.getByRole('button', { name: '登录系统' })
    const guestButton = page.getByRole('button', { name: '游客登录' })
    const getButtonRendering = (locator) => locator.evaluate((button) => {
      const style = getComputedStyle(button)
      return { transform: style.transform, filter: style.filter }
    })

    const loginRenderingBefore = await getButtonRendering(loginButton)
    await loginButton.hover()
    const loginRenderingAfter = await getButtonRendering(loginButton)
    const guestRenderingBefore = await getButtonRendering(guestButton)
    await guestButton.hover()
    const guestRenderingAfter = await getButtonRendering(guestButton)
    loginChecks.loginHoverRenderingStable = JSON.stringify(loginRenderingBefore) === JSON.stringify(loginRenderingAfter)
    loginChecks.guestHoverRenderingStable = JSON.stringify(guestRenderingBefore) === JSON.stringify(guestRenderingAfter)

    await page.getByRole('button', { name: '显示密码' }).click()
    loginChecks.passwordToggleChangesState = await page.evaluate(() => (
      document.querySelector('input[autocomplete="current-password"]')?.type === 'text' &&
      Boolean(document.querySelector('.password-toggle .lucide-eye-off'))
    ))
    await page.getByRole('button', { name: '隐藏密码' }).click()
    await page.screenshot({ path: path.join(outputDir, '01-login.png') })

    await page.getByRole('button', { name: '游客登录' }).click({ noWaitAfter: true })
    await page.waitForFunction(
      () => document.documentElement.classList.contains('is-route-transitioning'),
      null,
      { timeout: 10000 }
    )
    await page.waitForURL(/dashboard/, { timeout: 10000 })
    await page.waitForTimeout(120)
    await page.screenshot({ path: path.join(outputDir, '02-transition-120ms.png') })
    await page.waitForTimeout(260)
    await page.screenshot({ path: path.join(outputDir, '03-transition-380ms.png') })

    await page.waitForTimeout(420)
    await page.screenshot({ path: path.join(outputDir, '04-dashboard.png') })

    const checks = await page.evaluate(() => {
      const quickActions = [...document.querySelectorAll('.quick-actions button')]
      const wordmark = document.querySelector('.brand-copy strong')
      const composer = document.querySelector('.chat-composer textarea')
      const header = document.querySelector('.app-header')
      const headerStyle = header ? getComputedStyle(header) : null
      const headerDividerStyle = header ? getComputedStyle(header, '::after') : null

      return {
        route: location.hash,
        transitioningClassCleared: !document.documentElement.classList.contains('is-route-transitioning'),
        horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth,
        nativeViewTransitionSupported: typeof document.startViewTransition === 'function',
        dashboardEyeRemoved: !document.querySelector('.dashboard .brand-mark'),
        dashboardWordmarkUsesBrandGradient: Boolean(
          wordmark && getComputedStyle(wordmark).backgroundImage.includes('linear-gradient')
        ),
        brandSubtitleUpdated: document.querySelector('.brand-copy small')?.textContent.trim() === 'AI 内容鉴伪',
        historyIconsMatch: Boolean(
          document.querySelector('.header-button .lucide-clock-3') &&
          document.querySelector('.quick-actions .lucide-clock-3')
        ),
        headerHasNoHardDivider: headerStyle?.borderBottomWidth === '0px',
        headerUsesSoftGradientDivider: Boolean(
          headerDividerStyle &&
          headerDividerStyle.backgroundImage.includes('linear-gradient') &&
          Number(headerDividerStyle.opacity) < 1
        ),
        quickActionCount: quickActions.length,
        quickActionsAreChineseOnly: quickActions.every((button) => !button.querySelector('code') && !button.textContent.includes('/')),
        sourceVerificationRemoved: !quickActions.some((button) => button.textContent.includes('来源核验')),
        commandTipRemoved: !document.querySelector('.command-tip'),
        composerPlaceholderHasNoCommandPrompt: Boolean(composer && !composer.placeholder.includes('/') && !composer.placeholder.includes('命令'))
      }
    })
    Object.assign(checks, loginChecks)

    const brandButton = page.locator('.brand')
    const brandRenderingBefore = await brandButton.evaluate((brand) => {
      const style = getComputedStyle(brand)
      return { backgroundColor: style.backgroundColor, boxShadow: style.boxShadow, filter: style.filter }
    })
    await brandButton.hover()
    const brandRenderingAfter = await brandButton.evaluate((brand) => {
      const style = getComputedStyle(brand)
      return { backgroundColor: style.backgroundColor, boxShadow: style.boxShadow, filter: style.filter }
    })
    checks.brandHoverIsNeutral = JSON.stringify(brandRenderingBefore) === JSON.stringify(brandRenderingAfter)

    await page.evaluate(() => {
      window.__logoutSawAnimation = false
      const detectAnimation = () => {
        if (
          document.documentElement.classList.contains('is-route-transitioning') ||
          document.querySelector('.page-enter-active, .page-leave-active')
        ) window.__logoutSawAnimation = true
      }
      new MutationObserver(detectAnimation).observe(document.documentElement, {
        attributes: true,
        childList: true,
        subtree: true
      })
    })
    await page.getByRole('button', { name: '退出登录' }).click()
    await page.waitForURL(/login/, { timeout: 10000 })
    await page.waitForTimeout(100)
    checks.logoutAnimationRemoved = await page.evaluate(() => !window.__logoutSawAnimation)

    await page.getByRole('button', { name: '游客登录' }).click({ noWaitAfter: true })
    await page.waitForFunction(
      () => document.documentElement.classList.contains('is-route-transitioning'),
      null,
      { timeout: 10000 }
    )
    checks.loginTransitionPreserved = true
    await page.waitForURL(/dashboard/, { timeout: 10000 })
    await page.waitForTimeout(650)

    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.getByRole('button', { name: '退出登录' }).click()
    await page.waitForURL(/login/, { timeout: 10000 })
    await page.getByRole('button', { name: '游客登录' }).click()
    await page.waitForURL(/dashboard/, { timeout: 10000 })
    await page.waitForTimeout(180)
    checks.reducedMotionFallbackRoute = await page.evaluate(() => location.hash)
    checks.reducedMotionTransitionClassCleared = await page.evaluate(
      () => !document.documentElement.classList.contains('is-route-transitioning')
    )

    await page.setViewportSize({ width: 390, height: 844 })
    await page.waitForTimeout(100)
    checks.mobileHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth
    )
    await page.screenshot({ path: path.join(outputDir, '05-dashboard-mobile.png') })

    process.stdout.write(JSON.stringify({ checks, consoleErrors }, null, 2))
  } finally {
    await browser.close()
  }
}

run().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
