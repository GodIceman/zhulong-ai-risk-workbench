import {
  buildDemoArticleReport,
  isDemoMode,
  runDemoStatusSequence
} from '@/services/demoMode'

const API_BASES = ['http://localhost:5002', 'http://127.0.0.1:5002']
const TERMINAL_STATUSES = new Set(['completed', 'failed'])
const MAX_POLL_ATTEMPTS = 240

export const ARTICLE_TASK_STATUS_STEPS = [
  { key: 'received', label: '已接收文章' },
  { key: 'validating', label: '正在校验文章' },
  { key: 'routing', label: '正在进入本地文字分析流程' },
  { key: 'extracting', label: '正在准备代表性段落' },
  { key: 'detecting', label: '正在分析 AI 写作风格信号' },
  { key: 'aggregating', label: '正在汇总段落与核查线索' },
  { key: 'completed', label: '文字风险报告已生成' },
  { key: 'failed', label: '文字检测失败' }
]

const wait = (milliseconds) => new Promise((resolve) => {
  setTimeout(resolve, milliseconds)
})

const fetchWithTimeout = (url, options = {}, timeoutMs = 10000) => {
  const controller = new AbortController()
  const timerId = setTimeout(() => controller.abort(), timeoutMs)

  return fetch(url, {
    ...options,
    signal: controller.signal,
    cache: 'no-store'
  }).finally(() => clearTimeout(timerId))
}

const parseApiResponse = async (response) => {
  const data = await response.json().catch(() => ({}))
  if (!response.ok || data.success === false) {
    const error = new Error(
      data.error?.message
      || (typeof data.error === 'string' ? data.error : '')
      || `接口请求失败（${response.status}）`
    )
    error.isBackendResponseError = true
    throw error
  }
  return data
}

let activeApiBase = ''

const requestApi = async (path, options = {}, timeoutMs = 10000) => {
  const candidates = activeApiBase
    ? [activeApiBase, ...API_BASES.filter((baseUrl) => baseUrl !== activeApiBase)]
    : API_BASES
  let lastConnectionError = null

  for (const baseUrl of candidates) {
    try {
      const response = await fetchWithTimeout(`${baseUrl}${path}`, options, timeoutMs)
      const data = await parseApiResponse(response)
      activeApiBase = baseUrl
      return data
    } catch (error) {
      if (error?.isBackendResponseError) {
        throw error
      }
      lastConnectionError = error
    }
  }

  throw lastConnectionError || new Error('无法连接文章核查服务')
}

const createArticleTask = (payload) => requestApi('/api/articles/verify', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    input: {
      kind: 'text',
      title: payload.title ?? '',
      text: payload.text ?? '',
      declared_url: payload.declared_url ?? '',
      declared_author: payload.declared_author ?? '',
      declared_published_at: payload.declared_published_at ?? ''
    },
    options: {
      mode: 'local_ai_style',
      allow_network: false,
      max_material_claims: 20
    }
  })
}, 15000)

const getTaskStatus = (taskId) => requestApi(
  `/api/tasks/${encodeURIComponent(taskId)}`,
  {},
  10000
)

const getTaskReport = (taskId) => requestApi(
  `/api/tasks/${encodeURIComponent(taskId)}/report`,
  {},
  10000
)

const statusToUi = (status) => ({
  key: status.status,
  label: ARTICLE_TASK_STATUS_STEPS.find((step) => step.key === status.status)?.label
    || status.status,
  detail: status.message || '',
  progress: Number(status.progress || 0),
  taskId: status.task_id,
  timestamp: new Date().toISOString()
})

const articleRiskLabel = (riskLevel, verdict) => {
  if (verdict === 'failed' || verdict === 'text_detection_unavailable') return '检测未完成'
  return ({
    high: '高 AI 风格信号',
    medium: '中 AI 风格信号',
    low: '未见强 AI 信号',
    unknown: '无法确认'
  }[riskLevel] || '无法确认')
}

export const adaptArticleReport = (report, context = {}) => ({
  raw: report,
  taskId: report.task_id,
  mediaType: report.media_type || 'article',
  verdict: report.verdict,
  riskLevel: report.risk_level || 'unknown',
  riskLabel: articleRiskLabel(report.risk_level, report.verdict),
  summary: report.summary || '',
  metadata: report.metadata || {},
  decision: report.decision || {},
  article: {
    text_detection: report.article?.text_detection || {},
    sources: report.article?.sources || [],
    claims: report.article?.claims || [],
    missing_evidence: report.article?.missing_evidence || [],
    internal_consistency_issues: report.article?.internal_consistency_issues || []
  },
  warnings: report.limitations || [],
  generatedAt: report.created_at || new Date().toISOString(),
  inputName: report.metadata?.title || context.title || '未命名文章'
})

export const runArticleVerificationTask = async (payload, callbacks = {}) => {
  if (isDemoMode) {
    const taskId = `DEMO-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}-${Math.random().toString(36).slice(2, 10).toUpperCase()}`
    const task = {
      id: taskId,
      type: 'article',
      mediaType: 'article',
      inputKind: 'text',
      capability: '中文 AI 写作风格示例',
      title: payload.title || '未命名文章',
      createdAt: new Date().toISOString()
    }
    callbacks.onTask?.(task)
    await runDemoStatusSequence(callbacks, taskId, '文字')
    const report = buildDemoArticleReport({ taskId, title: payload.title })
    return {
      task,
      raw: report,
      report: adaptArticleReport(report, { title: payload.title })
    }
  }

  const created = await createArticleTask(payload)
  const task = {
    id: created.task_id,
    type: 'article',
    mediaType: 'article',
    inputKind: 'text',
    capability: '离线事实声明与来源清单',
    title: payload.title || '未命名文章',
    createdAt: new Date().toISOString()
  }

  callbacks.onTask?.(task)
  callbacks.onStatus?.(statusToUi({
    task_id: created.task_id,
    status: created.status || 'received',
    progress: 5,
    message: '已创建文章核查任务'
  }))

  let latestStatus = null
  for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
    await wait(attempt < 5 ? 400 : 1000)
    latestStatus = await getTaskStatus(created.task_id)
    callbacks.onStatus?.(statusToUi(latestStatus))
    if (TERMINAL_STATUSES.has(latestStatus.status)) {
      break
    }
  }

  if (!latestStatus || !TERMINAL_STATUSES.has(latestStatus.status)) {
    throw new Error('文章核查任务超时，请稍后重试')
  }

  const reportResponse = await getTaskReport(created.task_id)
  const report = reportResponse.report
  const adaptedReport = adaptArticleReport(report, { title: payload.title })

  return {
    task,
    raw: report,
    report: adaptedReport
  }
}

export const runArticleVerification = runArticleVerificationTask
