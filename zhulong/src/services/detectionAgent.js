import {
  buildDemoMediaReport,
  isDemoMode,
  runDemoStatusSequence
} from '@/services/demoMode'

export const TASK_STATUS_STEPS = [
  { key: 'received', label: '已接收文件' },
  { key: 'validating', label: '正在校验文件' },
  { key: 'routing', label: '正在识别媒体类型' },
  { key: 'extracting', label: '正在解析媒体信息' },
  { key: 'detecting', label: '正在执行模型检测' },
  { key: 'aggregating', label: '正在生成风险报告' },
  { key: 'completed', label: '检测完成' },
  { key: 'uncertain', label: '无法形成明确结论' },
  { key: 'failed', label: '检测失败' }
]

const API_BASES = ['http://localhost:5002', 'http://127.0.0.1:5002']
const IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp']
const VIDEO_EXTENSIONS = ['mp4', 'mov', 'avi', 'webm']
const TERMINAL_STATUSES = new Set(['completed', 'failed', 'uncertain'])

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

export const createTaskId = (prefix = 'TASK') => {
  const randomPart = typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID().slice(0, 8).toUpperCase()
    : Math.random().toString(36).slice(2, 10).toUpperCase()
  return `${prefix}-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}-${randomPart}`
}

const getExtension = (fileName = '') => fileName.split('.').pop()?.toLowerCase() || ''

export const detectInputType = ({ file, text } = {}) => {
  if (file) {
    const mime = file.type || ''
    const extension = getExtension(file.name)
    if (mime.startsWith('image/') || IMAGE_EXTENSIONS.includes(extension)) {
      return { type: 'image', inputKind: 'file' }
    }
    if (mime.startsWith('video/') || VIDEO_EXTENSIONS.includes(extension)) {
      return { type: 'video', inputKind: 'file' }
    }
    throw new Error('暂不支持该文件类型，请上传 JPG、PNG、WebP、MP4、MOV、AVI 或 WebM')
  }

  if (typeof text === 'string' && text.trim()) {
    return { type: 'article', inputKind: 'pasted_text' }
  }

  throw new Error('请粘贴要检测的文字，或上传图片、视频文件')
}

const fetchWithTimeout = (url, options = {}, timeoutMs = 60000) => {
  const controller = new AbortController()
  const timerId = setTimeout(() => controller.abort(), timeoutMs)
  return fetch(url, { ...options, signal: controller.signal, cache: 'no-store' })
    .finally(() => clearTimeout(timerId))
}

const parseApiResponse = async (response) => {
  const data = await response.json().catch(() => ({}))
  if (!response.ok || data.success === false) {
    const message = data.error?.message || data.error || `接口请求失败：${response.status}`
    throw new Error(message)
  }
  return data
}

const tryApiBases = async (factory, failureMessage) => {
  const errors = []
  for (const baseUrl of API_BASES) {
    try {
      return await factory(baseUrl)
    } catch (error) {
      errors.push(error?.message || String(error))
    }
  }
  throw new Error(`${failureMessage}。${errors.join('；')}`)
}

const uploadMedia = async (file, options = {}) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('options', JSON.stringify(options))

  return tryApiBases(async (baseUrl) => {
    const response = await fetchWithTimeout(`${baseUrl}/api/media/analyze`, {
      method: 'POST',
      body: formData
    }, 15000)
    return parseApiResponse(response)
  }, '统一媒体检测服务连接失败')
}

const getTaskStatus = async (taskId) => tryApiBases(async (baseUrl) => {
  const response = await fetchWithTimeout(`${baseUrl}/api/tasks/${taskId}`, {}, 10000)
  return parseApiResponse(response)
}, '任务状态查询失败')

const getTaskReport = async (taskId) => tryApiBases(async (baseUrl) => {
  const response = await fetchWithTimeout(`${baseUrl}/api/tasks/${taskId}/report`, {}, 10000)
  return parseApiResponse(response)
}, '风险报告读取失败')

const fileToDataUrl = (file) => new Promise((resolve) => {
  if (!file?.type?.startsWith('image/')) {
    resolve('')
    return
  }
  const reader = new FileReader()
  reader.onload = () => resolve(reader.result || '')
  reader.onerror = () => resolve('')
  reader.readAsDataURL(file)
})

const statusToUi = (status) => ({
  key: status.status,
  label: TASK_STATUS_STEPS.find((step) => step.key === status.status)?.label || status.status,
  detail: status.message,
  progress: status.progress,
  taskId: status.task_id,
  timestamp: new Date().toISOString()
})

const riskLabel = (riskLevel, verdict = '') => {
  if (riskLevel === 'unknown' && verdict === 'uncertain') return '无法确认'
  if (riskLevel === 'unknown' && verdict === 'failed') return '检测失败'
  return ({
    high: '高风险',
    medium: '中风险',
    low: '低风险',
    unknown: '未知'
  }[riskLevel] || '未知')
}

const verdictText = (report) => {
  const map = {
    ai_generated: '检测到 AI 生成风险',
    manipulated_suspected: '检测到疑似 AI 编辑或局部篡改风险',
    ai_generated_video_suspected: '检测到完整 AI 生成视频信号',
    face_manipulation_suspected: '检测到人脸换脸或操纵信号',
    multiple_video_ai_signals: '检测到多种视频 AI 伪造信号',
    likely_real: '当前未发现明显 AI 生成风险',
    uncertain: '当前无法确认',
    failed: '检测未完成'
  }
  return map[report.verdict] || '检测完成'
}

const percent = (value) => {
  if (value == null || Number.isNaN(Number(value))) return null
  const numeric = Number(value)
  return Math.round((numeric <= 1 ? numeric * 100 : numeric) * 10) / 10
}

const reportEngine = (report) => {
  const qualityStatus = report.decision?.quality?.status
  const primaryModel = report.models?.[0]
  if (report.verdict === 'failed' || primaryModel?.error) {
    return { type: 'failed', label: '主模型未完成调用' }
  }
  if (qualityStatus === 'degraded') {
    return { type: 'degraded', label: '辅助模型降级' }
  }
  if (qualityStatus === 'experimental') {
    return { type: 'experimental', label: '实验性模型信号' }
  }
  if (qualityStatus === 'primary_only') {
    return { type: 'primary', label: '仅主模型检测' }
  }
  return { type: 'model', label: '多证据检测完成' }
}

export const adaptBackendReport = (report, context = {}) => ({
  raw: report,
  taskId: report.task_id,
  type: report.media_type,
  mediaType: report.media_type,
  inputKind: 'file',
  inputName: report.metadata?.filename || context.inputName || '媒体文件',
  verdict: report.verdict,
  conclusion: verdictText(report),
  summary: report.summary,
  riskLevel: report.risk_level || 'unknown',
  riskLabel: riskLabel(report.risk_level, report.verdict),
  confidence: percent(report.confidence),
  capabilities: report.media_type === 'video'
    ? ['完整 AI 生视频检测', '人脸换脸检测', '时序辅助分析']
    : ['图片 AI 生成检测', '基础元数据读取'],
  evidence: (report.evidence || []).map((item, index) => ({
    id: item.id || `evidence-${index + 1}`,
    title: item.title || `证据 ${index + 1}`,
    description: item.description || '',
    severity: item.severity || report.risk_level || 'unknown',
    confidence: percent(item.confidence),
    modelScore: percent(item.model_score),
    signals: item.signals || [],
    time: item.timestamp
  })),
  visualization: normalizeVisualization(report, context),
  metadata: report.metadata || {},
  models: report.models || [],
  decision: report.decision || {},
  warnings: report.limitations || [],
  engine: reportEngine(report),
  generatedAt: report.created_at
})

const normalizeVisualization = (report, context) => {
  if (report.media_type === 'video') {
    return {
      kind: 'timeline',
      videoUrl: context.previewUrl || '',
      keyFrames: report.visualization?.key_frames || [],
      segments: report.visualization?.timeline || [],
      framePredictions: report.visualization?.frame_predictions || [],
      branches: report.visualization?.branches || {},
      duration: report.metadata?.duration || report.metadata?.duration_seconds || 0
    }
  }
  return {
    kind: 'image',
    imageUrl: context.previewUrl || '',
    regions: []
  }
}

export const runDetectionTask = async (payload, callbacks = {}) => {
  const detected = detectInputType(payload)
  const previewUrl = payload.previewUrl || await fileToDataUrl(payload.file)

  if (isDemoMode) {
    const taskId = createTaskId('DEMO')
    const task = {
      id: taskId,
      type: detected.type,
      inputKind: detected.inputKind,
      capability: detected.type === 'video' ? '视频联合鉴伪' : '图片检测',
      createdAt: new Date().toISOString()
    }
    callbacks?.onTask?.(task)
    await runDemoStatusSequence(callbacks, taskId, detected.type === 'video' ? '视频' : '图片')
    const report = buildDemoMediaReport({
      taskId,
      mediaType: detected.type,
      inputName: payload.file?.name
    })
    return {
      task,
      raw: report,
      report: adaptBackendReport(report, {
        inputName: payload.file?.name,
        previewUrl
      })
    }
  }

  const created = await uploadMedia(payload.file, {
    source_hint: payload.sourceHint || 'auto'
  })
  const task = {
    id: created.task_id,
    type: detected.type,
    inputKind: detected.inputKind,
    capability: detected.type === 'video' ? '视频联合鉴伪' : '图片检测',
    createdAt: new Date().toISOString()
  }

  callbacks?.onTask?.(task)
  callbacks?.onStatus?.(statusToUi({
    task_id: created.task_id,
    status: created.status || 'received',
    progress: 5,
    message: '已创建检测任务'
  }))

  let latestStatus = null
  for (let attempt = 0; attempt < 240; attempt += 1) {
    await wait(attempt < 5 ? 400 : 1000)
    latestStatus = await getTaskStatus(created.task_id)
    callbacks?.onStatus?.(statusToUi(latestStatus))
    if (TERMINAL_STATUSES.has(latestStatus.status)) break
  }

  if (!latestStatus || !TERMINAL_STATUSES.has(latestStatus.status)) {
    throw new Error('检测任务超时，请稍后在历史记录中查看或重试')
  }

  const { report } = await getTaskReport(created.task_id)
  return {
    task,
    raw: report,
    report: adaptBackendReport(report, {
      inputName: payload.file?.name,
      previewUrl
    })
  }
}

export const normalizeImageResult = (result, context = {}) => {
  if (result?.task_id) return adaptBackendReport(result, context)
  return adaptBackendReport({
    task_id: context.taskId || createTaskId('IMG'),
    media_type: 'image',
    verdict: 'failed',
    risk_level: 'unknown',
    confidence: null,
    summary: '未收到统一后端报告，无法形成真伪判断。',
    evidence: [],
    visualization: {},
    metadata: { filename: context.inputName },
    models: [],
    limitations: ['请通过统一上传入口重新检测。'],
    created_at: new Date().toISOString()
  }, context)
}

export const generateLocalImageResult = async (_previewUrl, file, fallbackReason = '') => ({
  task_id: createTaskId('IMG'),
  media_type: 'image',
  verdict: 'failed',
  risk_level: 'unknown',
  confidence: null,
  summary: '模型服务不可用，未形成真伪判断。',
  evidence: [],
  visualization: {},
  metadata: { filename: file?.name },
  models: [{
    model_id: 'ai-image-detector',
    model_version: 'unknown',
    engine_type: 'model',
    score: null,
    label: 'failed',
    latency_ms: 0,
    error: fallbackReason
  }],
  limitations: ['本次没有成功调用模型，不输出真伪结论。'],
  created_at: new Date().toISOString()
})

export const createAnnotatedImage = async (imageUrl) => imageUrl || ''

export const formatTime = (seconds) => {
  const safeSeconds = Number(seconds)
  if (!Number.isFinite(safeSeconds) || safeSeconds < 0) return '0:00'
  const minutes = Math.floor(safeSeconds / 60)
  const remain = Math.floor(safeSeconds % 60)
  return `${minutes}:${String(remain).padStart(2, '0')}`
}
