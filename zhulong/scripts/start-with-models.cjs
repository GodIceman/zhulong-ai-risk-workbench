const net = require('net')
const http = require('http')
const path = require('path')
const fs = require('fs')
const { spawn } = require('child_process')

const appRoot = path.resolve(__dirname, '..')
const repoRoot = path.resolve(appRoot, '..')
const isWindows = process.platform === 'win32'
const frontendPort = 3000
const frontendUrl = `http://127.0.0.1:${frontendPort}/#/login`
const logRoot = path.join(repoRoot, 'logs')

const services = [
  {
    name: 'unified media API',
    port: 5002,
    healthPaths: ['/api/info'],
    cwd: repoRoot,
    python: path.join(repoRoot, '.venv-lrfimd', 'Scripts', 'python.exe'),
    script: path.join(repoRoot, 'unified_media_api.py'),
    logName: 'unified-media-api.log',
    env: {
      AI_DETECTOR_URL: 'http://127.0.0.1:5004',
      DEEPFAKE_URL: 'http://127.0.0.1:5003'
    }
  },
  {
    name: 'AI image and text detector',
    port: 5004,
    healthPaths: ['/api/ai/health', '/api/text/health'],
    cwd: repoRoot,
    python: path.join(repoRoot, '.venv-video-forensics', 'Scripts', 'python.exe'),
    script: path.join(repoRoot, 'ai_image_api.py'),
    logName: 'ai-image-text-detector.log',
    env: {
      AI_DETECTOR_DEVICE: 'auto'
    }
  },
  {
    name: 'AI video forensics ensemble',
    port: 5003,
    healthPaths: ['/api/video/health'],
    cwd: repoRoot,
    python: path.join(repoRoot, '.venv-video-forensics', 'Scripts', 'python.exe'),
    script: path.join(repoRoot, 'video_face_api.py'),
    logName: 'video-forensics.log'
  }
]

function isPortOpen(port) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: '127.0.0.1', port })
    const done = (open) => {
      socket.destroy()
      resolve(open)
    }
    socket.setTimeout(800)
    socket.once('connect', () => done(true))
    socket.once('timeout', () => done(false))
    socket.once('error', () => done(false))
  })
}

function getHttpResponse(url) {
  return new Promise((resolve) => {
    const request = http.get(url, { timeout: 1500 }, (response) => {
      let body = ''
      response.setEncoding('utf8')
      response.on('data', (chunk) => {
        if (body.length < 1024 * 1024) body += chunk
      })
      response.on('end', () => {
        resolve({
          ok: response.statusCode >= 200 && response.statusCode < 300,
          statusCode: response.statusCode,
          body
        })
      })
    })
    request.once('timeout', () => {
      request.destroy()
      resolve({ ok: false, statusCode: null, body: '' })
    })
    request.once('error', () => resolve({ ok: false, statusCode: null, body: '' }))
  })
}

async function isHttpReady(url) {
  return (await getHttpResponse(url)).ok
}

async function isZhulongFrontendReady() {
  const response = await getHttpResponse(`http://127.0.0.1:${frontendPort}/`)
  return response.ok && (
    response.body.includes('烛龙 AI 鉴伪系统')
    || response.body.includes('/src/main.js')
  )
}

async function isServiceReady(service) {
  const results = await Promise.all(
    service.healthPaths.map((healthPath) => (
      isHttpReady(`http://127.0.0.1:${service.port}${healthPath}`)
    ))
  )
  return results.every(Boolean)
}

function startService(service) {
  if (!fs.existsSync(service.python)) {
    throw new Error(`${service.name}: Python not found at ${service.python}`)
  }
  if (!fs.existsSync(service.script)) {
    throw new Error(`${service.name}: script not found at ${service.script}`)
  }

  fs.mkdirSync(logRoot, { recursive: true })
  const logPath = path.join(logRoot, service.logName)
  const logStream = fs.openSync(logPath, 'a')

  console.log(`[start] ${service.name} on port ${service.port}; log: ${logPath}`)
  const child = spawn(service.python, [service.script], {
    cwd: service.cwd,
    detached: true,
    windowsHide: true,
    env: {
      ...process.env,
      ...(service.env || {}),
      PORT: String(service.port),
      HOST: '127.0.0.1'
    },
    stdio: ['ignore', logStream, logStream]
  })
  child.unref()
}

async function ensureServices() {
  for (const service of services) {
    const portOpen = await isPortOpen(service.port)
    if (portOpen && await isServiceReady(service)) {
      console.log(`[ok] ${service.name} is healthy on port ${service.port}`)
    } else if (portOpen) {
      console.log(
        `[wait] Port ${service.port} is open, but ${service.name} has not passed all health checks yet`
      )
    } else {
      startService(service)
    }
  }
}

function startFrontend() {
  const viteBin = path.join(appRoot, 'node_modules', 'vite', 'bin', 'vite.js')
  if (!fs.existsSync(viteBin)) {
    console.error(`[error] Vite entry was not found at ${viteBin}. Run npm install in ${appRoot}.`)
    process.exit(1)
  }

  const child = spawn(process.execPath, [viteBin, '--host', '127.0.0.1'], {
    cwd: appRoot,
    stdio: 'inherit'
  })

  child.on('error', (error) => {
    console.error('[error] Failed to start frontend:', error)
    process.exit(1)
  })

  child.on('exit', (code, signal) => {
    if (signal) process.kill(process.pid, signal)
    process.exit(code ?? 0)
  })

  return child
}

async function ensureFrontend() {
  if (await isPortOpen(frontendPort)) {
    if (!await isZhulongFrontendReady()) {
      throw new Error(
        `Port ${frontendPort} is occupied by another program. Stop that program, then start Zhulong again.`
      )
    }
    console.log(`[ok] Zhulong frontend is already running on port ${frontendPort}`)
    return false
  }

  console.log('[info] Starting frontend. Model services may need a little time to finish loading.')
  startFrontend()
  return true
}

async function waitForFrontend() {
  for (let i = 0; i < 40; i += 1) {
    if (await isZhulongFrontendReady()) return true
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  return false
}

async function waitForModelServices() {
  const checks = [
    ['unified API', 'http://127.0.0.1:5002/api/info'],
    ['AI image model', 'http://127.0.0.1:5004/api/ai/health'],
    ['AI text model', 'http://127.0.0.1:5004/api/text/health'],
    ['video forensics models', 'http://127.0.0.1:5003/api/video/health']
  ]
  for (let attempt = 0; attempt < 360; attempt += 1) {
    const results = await Promise.all(checks.map(([, url]) => isHttpReady(url)))
    if (results.every(Boolean)) return true
    if (attempt === 0 || (attempt + 1) % 15 === 0) {
      const pending = checks
        .filter((_, index) => !results[index])
        .map(([name]) => name)
        .join(', ')
      console.log(`[wait] Model services are loading: ${pending}`)
    }
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
  return false
}

async function openFrontendInBrowser() {
  const ready = await waitForFrontend()
  if (!ready) {
    console.log(`[warn] Frontend did not respond on ${frontendUrl} yet. Open it manually after it finishes loading.`)
    return false
  }

  console.log(`[open] ${frontendUrl}`)
  if (isWindows) {
    spawn(
      'rundll32.exe',
      ['url.dll,FileProtocolHandler', frontendUrl],
      { detached: true, stdio: 'ignore', windowsHide: true }
    ).unref()
  } else if (process.platform === 'darwin') {
    spawn('open', [frontendUrl], { detached: true, stdio: 'ignore' }).unref()
  } else {
    spawn('xdg-open', [frontendUrl], { detached: true, stdio: 'ignore' }).unref()
  }
  return true
}

async function reportModelReadiness() {
  const modelsReady = await waitForModelServices()
  if (modelsReady) {
    console.log('[ok] Image, text, and video model services are ready')
  } else {
    console.log('[warn] Some model services are still loading. The page is available, but detection may need more time.')
  }
}

async function main() {
  await ensureServices()
  const frontendStarted = await ensureFrontend()
  if (!frontendStarted) {
    await openFrontendInBrowser()
    return
  }

  setTimeout(() => {
    openFrontendInBrowser()
    reportModelReadiness()
  }, 100)
}

if (require.main === module) {
  main()
    .catch((error) => {
      console.error('[error] Failed to start Zhulong:', error.message || error)
      process.exit(1)
    })
}

module.exports = {
  ensureFrontend,
  ensureServices,
  getHttpResponse,
  isHttpReady,
  isPortOpen,
  isServiceReady,
  isZhulongFrontendReady,
  main,
  openFrontendInBrowser,
  reportModelReadiness,
  waitForFrontend,
  waitForModelServices
}
