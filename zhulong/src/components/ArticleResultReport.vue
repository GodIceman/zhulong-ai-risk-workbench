<template>
  <article v-if="report" class="article-report essential-report" :class="`priority-${priority}`">
    <header class="essential-header">
      <div class="status-line">
        <span class="priority-badge">{{ priorityLabel }}</span>
        <span class="scope-badge">实验性本地模型</span>
      </div>
      <h2>{{ verdictTitle }}</h2>
      <p>{{ summary }}</p>
    </header>

    <div class="essential-core">
      <section class="essential-signal">
        <span>AI 风格综合信号</span>
        <strong :class="{ 'risk-percent': aiSignalLabel !== '—' }">{{ aiSignalLabel }}</strong>
        <small>风格信号不证明作者身份</small>
      </section>

      <section class="essential-action">
        <span>建议下一步</span>
        <p>{{ nextAction }}</p>
      </section>
    </div>

    <section class="essential-findings">
      <div class="essential-section-heading">
        <div>
          <span>核心依据</span>
          <h3>最需要关注的段落</h3>
        </div>
        <small>{{ Math.min(priorityTextSegments.length, 2) }} 项</small>
      </div>

      <ol v-if="priorityTextSegments.length">
        <li
          v-for="(segment, index) in priorityTextSegments.slice(0, 2)"
          :key="segment.segment_id || `essential-segment-${segment.index}`"
        >
          <span class="finding-index">{{ String(index + 1).padStart(2, '0') }}</span>
          <div>
            <strong>{{ segmentSignalLabel(segment.signal_level) }}</strong>
            <p>{{ segment.text || '未保留段落摘录' }}</p>
          </div>
        </li>
      </ol>
      <p v-else class="essential-empty">本次没有可展示的重点段落，建议补充正文后重新分析。</p>
    </section>

    <footer class="essential-footer">
      <p>写作风格信号不证明作者身份，也不构成文章真假结论。</p>
    </footer>
  </article>

  <article v-else-if="false" class="article-report" :class="`priority-${priority}`">
    <header class="report-header">
      <div class="verdict-copy">
        <div class="status-line">
          <span class="priority-badge">{{ priorityLabel }}</span>
          <span class="scope-badge">实验性本地模型</span>
        </div>
        <h2>{{ verdictTitle }}</h2>
        <p class="summary">{{ summary }}</p>
        <div class="next-action">
          <span>建议下一步</span>
          <p>{{ nextAction }}</p>
        </div>
      </div>

      <dl class="header-facts">
        <div>
          <dt>AI 风格综合信号</dt>
          <dd>{{ aiSignalLabel }}</dd>
        </div>
        <div>
          <dt>分析段落</dt>
          <dd>{{ textSegments.length }} 段</dd>
        </div>
        <div>
          <dt>完成时间</dt>
          <dd>{{ generatedAt }}</dd>
        </div>
      </dl>
    </header>

    <div class="report-body">
      <section class="panel coverage-panel" aria-label="核查结果概览">
        <div class="section-heading">
          <div>
            <span>AI WRITING SIGNAL</span>
            <h3>文字风格分析</h3>
          </div>
          <small>分类器分数不是作者身份概率</small>
        </div>

        <div class="snapshot-grid">
          <div class="snapshot-primary">
            <span>AI 风格综合信号</span>
            <strong>{{ aiSignalLabel }}</strong>
            <div
              class="progress-track"
              role="progressbar"
              aria-label="AI 风格综合信号"
              :aria-valuenow="aiSignalPercent"
              aria-valuemin="0"
              aria-valuemax="100"
            >
              <span :style="{ width: `${aiSignalPercent}%` }"></span>
            </div>
            <small>{{ textSignalSummary }}</small>
          </div>
          <div class="snapshot-metric metric-alert">
            <span>强信号段落</span>
            <strong>{{ strongSegmentPercent }}%</strong>
            <small>{{ strongSegments.length }} / {{ textSegments.length }} 段</small>
          </div>
          <div class="snapshot-metric">
            <span>正文采样覆盖</span>
            <strong>{{ textCoveragePercent }}%</strong>
            <small>最长分析 {{ textSegments.length }} 个代表性段落</small>
          </div>
        </div>
      </section>

      <section class="panel claims-panel">
        <div class="section-heading">
          <div>
            <span>SEGMENT SIGNALS</span>
            <h3>重点段落</h3>
          </div>
          <small>按 AI 风格信号从高到低展示 {{ priorityTextSegments.length }} 段</small>
        </div>

        <ol v-if="priorityTextSegments.length" class="claim-list priority-claim-list text-signal-list">
          <li
            v-for="segment in priorityTextSegments"
            :key="segment.segment_id || `segment-${segment.index}`"
            class="claim-card"
            :class="`signal-${segment.signal_level || 'mixed'}`"
          >
            <div class="claim-head">
              <div class="claim-identifiers">
                <span>{{ segment.segment_id || `段落 ${segment.index + 1}` }}</span>
                <span>{{ segment.token_count || '—' }} tokens</span>
              </div>
              <span class="assessment-badge" :class="`signal-${segment.signal_level || 'mixed'}`">
                AI 风格信号 {{ percentLabel(segment.ai_signal_score) }}
              </span>
            </div>

            <blockquote>{{ segment.text || '未保留段落摘录' }}</blockquote>
            <p class="claim-reason">{{ segmentSignalLabel(segment.signal_level) }}</p>
          </li>
        </ol>

        <div v-else class="empty-state">
          <strong>没有可展示的模型段落</strong>
          <p>正文可能过短，或文字模型未成功完成调用。</p>
        </div>
      </section>

      <details class="details-panel report-details">
        <summary>
          <div>
            <strong>查看完整核查明细</strong>
            <span>{{ textSegments.length }} 个模型段落、{{ claims.length }} 条声明与 {{ sources.length }} 个来源</span>
          </div>
        </summary>

        <div class="details-content">
          <section class="detail-section full-text-signal-section">
            <div class="section-heading">
              <div>
                <span>ALL SEGMENTS</span>
                <h3>完整段落信号</h3>
              </div>
              <small>{{ textSegments.length }} 段</small>
            </div>

            <ol v-if="textSegments.length" class="segment-detail-list">
              <li
                v-for="segment in textSegments"
                :key="segment.segment_id || `detail-segment-${segment.index}`"
                :class="`signal-${segment.signal_level || 'mixed'}`"
              >
                <div>
                  <strong>{{ segment.segment_id || `段落 ${segment.index + 1}` }}</strong>
                  <span>{{ segmentSignalLabel(segment.signal_level) }}</span>
                </div>
                <p>{{ segment.text || '未保留段落摘录' }}</p>
                <b>{{ percentLabel(segment.ai_signal_score) }}</b>
              </li>
            </ol>

            <div v-else class="empty-state">
              <strong>没有段落级模型结果</strong>
              <p>请确认正文长度满足要求，并检查文字模型是否已完成加载。</p>
            </div>
          </section>

          <section class="detail-section full-claims-section">
            <div class="section-heading">
              <div>
                <span>ALL CLAIMS</span>
                <h3>完整声明清单</h3>
              </div>
              <small>{{ claims.length }} 条</small>
            </div>

            <ol v-if="claims.length" class="claim-list">
              <li
                v-for="(claim, index) in claims"
                :key="claim.claim_id || `claim-${index}`"
                class="claim-card"
                :class="`assessment-${claim.assessment || 'unknown'}`"
              >
                <div class="claim-head">
                  <div class="claim-identifiers">
                    <span>{{ claim.claim_id || `声明 ${index + 1}` }}</span>
                    <span>{{ materialityLabel(claim.materiality) }}</span>
                    <span v-if="claim.checkability === 'out_of_scope'">范围外</span>
                  </div>
                  <span class="assessment-badge">{{ assessmentLabel(claim.assessment) }}</span>
                </div>

                <blockquote>{{ claim.source_span?.quote || claim.text || '未保留原文摘录' }}</blockquote>

                <dl class="claim-meta">
                  <div>
                    <dt>原文位置</dt>
                    <dd>{{ sourceSpanLabel(claim) }}</dd>
                  </div>
                  <div>
                    <dt>核查说明</dt>
                    <dd>{{ assessmentReasonLabel(claim.assessment_reason) }}</dd>
                  </div>
                </dl>

                <div v-if="claim.evidence_links?.length" class="evidence-links">
                  <h4>关联证据</h4>
                  <ul>
                    <li
                      v-for="(evidence, evidenceIndex) in claim.evidence_links"
                      :key="evidence.evidence_id || evidence.source_id || evidenceIndex"
                    >
                      <strong>{{ evidenceRelationLabel(evidence.relation) }}</strong>
                      <span>{{ evidence.excerpt || evidence.source_id || formatValue(evidence) }}</span>
                    </li>
                  </ul>
                </div>

                <div v-if="claim.missing_evidence?.length" class="missing-evidence">
                  <h4>待补充证据</h4>
                  <ul>
                    <li v-for="item in claim.missing_evidence" :key="item">{{ item }}</li>
                  </ul>
                </div>
              </li>
            </ol>

            <div v-else class="empty-state">
              <strong>没有可展示的声明清单</strong>
              <p>这可能表示未识别到适合客观核验的事实声明，或本次核查流程未完成。</p>
            </div>
          </section>

          <section class="detail-section sources-panel">
            <div class="section-heading">
              <div>
                <span>SOURCE INVENTORY</span>
                <h3>来源清单</h3>
              </div>
              <small>{{ sources.length }} 个</small>
            </div>

            <ul v-if="sources.length" class="source-list">
              <li v-for="(source, index) in sources" :key="source.source_id || source.canonical_url || index">
                <div class="source-main">
                  <span class="source-id">{{ source.source_id || `来源 ${index + 1}` }}</span>
                  <div>
                    <a
                      v-if="safeSourceUrl(source)"
                      :href="safeSourceUrl(source)"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {{ source.title || source.domain || safeSourceUrl(source) }}
                    </a>
                    <strong v-else>{{ source.title || source.domain || '未命名来源' }}</strong>
                    <p>{{ source.publisher || source.domain || '未提供发布主体' }}</p>
                  </div>
                </div>

                <div class="source-status">
                  <span :class="`status-${source.verification_status || 'unknown'}`">
                    {{ sourceStatusLabel(source.verification_status) }}
                  </span>
                  <small>{{ sourceRoleLabel(source.source_role) }} · {{ sourceClassLabel(source.source_class) }}</small>
                </div>

                <dl class="source-meta">
                  <div>
                    <dt>发布日期</dt>
                    <dd>{{ source.published_at || '未提供' }}</dd>
                  </div>
                  <div>
                    <dt>获取时间</dt>
                    <dd>{{ source.retrieved_at ? formatDate(source.retrieved_at) : '未获取' }}</dd>
                  </div>
                </dl>

                <ul v-if="source.quality_flags?.length" class="quality-flags">
                  <li v-for="flag in source.quality_flags" :key="flag">{{ qualityFlagLabel(flag) }}</li>
                </ul>
              </li>
            </ul>

            <div v-else class="empty-state">
              <strong>没有登记来源</strong>
              <p>请优先补充原始公告、数据报告、研究材料或可定位的完整采访记录。</p>
            </div>
          </section>

          <section class="detail-section">
            <h4>运行信息</h4>
            <dl class="technical-grid">
              <div>
                <dt>分析模式</dt>
                <dd>{{ modeLabel }}</dd>
              </div>
              <div>
                <dt>文字模型</dt>
                <dd>{{ textDetection.model_version || textDetection.model_id || '未提供' }}</dd>
              </div>
              <div>
                <dt>模型版本</dt>
                <dd>{{ textDetection.model_revision || '未提供' }}</dd>
              </div>
              <div>
                <dt>联网请求</dt>
                <dd>{{ networkRequested ? '已请求' : '未请求' }}</dd>
              </div>
              <div>
                <dt>实际联网</dt>
                <dd>{{ networkUsed ? '已使用' : '未使用' }}</dd>
              </div>
              <div>
                <dt>检索失败</dt>
                <dd>{{ retrievalFailures }} 项</dd>
              </div>
              <div>
                <dt>文章标题</dt>
                <dd>{{ metadata.title || '未命名文章' }}</dd>
              </div>
              <div>
                <dt>内容指纹</dt>
                <dd>{{ metadata.content_sha256 || '未提供' }}</dd>
              </div>
            </dl>
          </section>

          <section v-if="declaredOriginEntries.length" class="detail-section">
            <h4>用户声明的来源信息</h4>
            <dl class="technical-grid">
              <div v-for="item in declaredOriginEntries" :key="item.key">
                <dt>{{ item.label }}</dt>
                <dd>{{ item.value }}</dd>
              </div>
            </dl>
            <p class="origin-note">这些信息尚未自动验证，仅作为后续核查线索。</p>
          </section>

          <section class="detail-section limitations">
            <h4>能力限制</h4>
            <ul>
              <li v-for="item in limitations" :key="item">{{ item }}</li>
            </ul>
          </section>
        </div>
      </details>
    </div>

    <footer>
      <span>{{ taskId }}</span>
      <p>本报告展示实验性写作风格信号，不证明作者身份，也不构成文章真假结论。</p>
    </footer>
  </article>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  report: {
    type: Object,
    default: null
  }
})

const rawReport = computed(() => props.report?.raw || props.report || {})
const taskId = computed(() => props.report?.taskId || rawReport.value.task_id || '')
const verdict = computed(() => props.report?.verdict || rawReport.value.verdict || 'failed')
const priority = computed(() => props.report?.riskLevel || rawReport.value.risk_level || 'unknown')
const metadata = computed(() => props.report?.metadata || rawReport.value.metadata || {})
const decision = computed(() => props.report?.decision || rawReport.value.decision || {})
const coverage = computed(() => decision.value.coverage || {})
const article = computed(() => rawReport.value.article || {})
const visualization = computed(() => rawReport.value.visualization || {})
const claims = computed(() => article.value.claims || visualization.value.claims || [])
const sources = computed(() => article.value.sources || visualization.value.sources || [])
const textDetection = computed(() => (
  article.value.text_detection
  || props.report?.article?.text_detection
  || {}
))
const textSegments = computed(() => (
  textDetection.value.segments
  || visualization.value.text_segments
  || []
))
const aiSignalPercent = computed(() => {
  const value = Number(
    textDetection.value.ai_signal_score
    ?? textDetection.value.score
    ?? metadata.value.ai_style_signal_score
  )
  if (!Number.isFinite(value)) return 0
  return Math.min(100, Math.max(0, Math.round((value <= 1 ? value * 100 : value))))
})
const aiSignalLabel = computed(() => (
  textDetection.value.ai_signal_score == null
  && textDetection.value.score == null
  && metadata.value.ai_style_signal_score == null
    ? '—'
    : `${aiSignalPercent.value}%`
))
const strongSegments = computed(() => textSegments.value.filter((item) => (
  item.signal_level === 'high' || Number(item.ai_signal_score) >= 0.85
)))
const strongSegmentPercent = computed(() => {
  if (!textSegments.value.length) return 0
  const modelRatio = Number(textDetection.value.strong_ai_segment_ratio)
  if (Number.isFinite(modelRatio) && modelRatio >= 0) {
    return Math.min(100, Math.round(modelRatio * 100))
  }
  return Math.round((strongSegments.value.length / textSegments.value.length) * 100)
})
const textCoveragePercent = computed(() => {
  const value = Number(
    textDetection.value.analysis_coverage
    ?? metadata.value.text_analysis_coverage
  )
  return Number.isFinite(value) ? Math.min(100, Math.round(value * 100)) : 0
})
const priorityTextSegments = computed(() => [...textSegments.value]
  .sort((left, right) => (
    Number(right.ai_signal_score || 0) - Number(left.ai_signal_score || 0)
  ))
  .slice(0, 3))
const textSignalSummary = computed(() => {
  if (verdict.value === 'ai_style_suspected') return '多个代表性段落形成一致高信号'
  if (verdict.value === 'no_strong_ai_signal') return '当前未形成一致的强 AI 写作信号'
  if (verdict.value === 'insufficient_text') return '正文长度不足，未形成稳定判断'
  if (verdict.value === 'text_detection_unavailable' || verdict.value === 'failed') {
    return '文字模型未成功完成调用'
  }
  return '段落信号混合或处于模型灰区'
})
const priorityClaims = computed(() => {
  const assessmentOrder = {
    contradicted: 0,
    mixed: 1,
    insufficient_evidence: 2,
    not_checked: 3,
    supported: 4,
    out_of_scope: 5
  }
  const materialityOrder = { high: 0, medium: 1, low: 2 }

  return claims.value
    .map((claim, originalIndex) => ({ ...claim, originalIndex }))
    .sort((left, right) => (
      (assessmentOrder[left.assessment] ?? 6) - (assessmentOrder[right.assessment] ?? 6)
      || (materialityOrder[left.materiality] ?? 3) - (materialityOrder[right.materiality] ?? 3)
      || left.originalIndex - right.originalIndex
    ))
    .slice(0, 2)
})

const asCount = (value) => {
  const numeric = Number(value)
  return Number.isFinite(numeric) && numeric >= 0 ? Math.floor(numeric) : 0
}

const candidateClaims = computed(() => asCount(coverage.value.candidate_claims ?? claims.value.length))
const materialClaims = computed(() => asCount(coverage.value.material_claims))
const checkedClaims = computed(() => asCount(coverage.value.checked_claims))
const supportedClaims = computed(() => asCount(coverage.value.supported_claims))
const conflictedClaims = computed(() => asCount(coverage.value.conflicted_claims))
const insufficientClaims = computed(() => asCount(coverage.value.insufficient_claims))
const explicitSources = computed(() => asCount(coverage.value.explicit_sources ?? sources.value.length))
const verifiedSources = computed(() => asCount(coverage.value.verified_sources))
const coveragePercent = computed(() => {
  if (!materialClaims.value) return 0
  return Math.min(100, Math.round((checkedClaims.value / materialClaims.value) * 100))
})

const priorityLabel = computed(() => ({
  high: '高 AI 风格信号',
  medium: '中 AI 风格信号',
  low: '未见强 AI 信号',
  unknown: '当前无法确认'
}[priority.value] || '当前无法确认'))

const verdictTitle = computed(() => ({
  ai_style_suspected: '检测到较强 AI 写作风格信号',
  no_strong_ai_signal: '当前未发现一致的强 AI 写作信号',
  uncertain: '段落信号不一致，当前无法确认',
  insufficient_text: '正文过短，无法稳定分析',
  text_detection_unavailable: '文字模型未完成调用',
  insufficient_evidence: '证据不足，需继续核验',
  no_checkable_claims: '未识别到可客观核验的声明',
  claim_conflicts_found: '发现声明证据冲突',
  supported_within_scope: '本次核查范围内获得支持',
  failed: '核查未完成'
}[verdict.value] || '核查状态待确认'))

const summary = computed(() => (
  props.report?.summary
  || rawReport.value.summary
  || '本次核查没有返回可展示的摘要。'
))

const nextAction = computed(() => ({
  ai_style_suspected: '查看高信号段落，并结合写作过程、版本记录和原始材料进行人工复核。',
  no_strong_ai_signal: '结果只能说明当前模型未见强信号；不要据此证明文章一定由人类撰写。',
  uncertain: '增加正文长度或检查人机混写、重度改写情况，并保留无法确认结论。',
  insufficient_text: '至少提供约 100 个连续中文字后重新分析。',
  text_detection_unavailable: '确认文字模型已完成下载和加载后重试。',
  insufficient_evidence: '按各声明的待补充证据清单收集原始材料，并逐项完成外部核验。',
  no_checkable_claims: '确认输入是否包含可客观核验的时间、数值、归属或事件声明。',
  claim_conflicts_found: '优先复核冲突声明、相反证据及其时间与适用范围，保留来源快照。',
  supported_within_scope: '确认重要声明和来源覆盖完整；范围外内容仍需单独审阅。',
  failed: '检查输入内容和核查服务后重试，本次结果不应作为事实依据。'
}[verdict.value] || '根据声明清单与来源状态安排人工复核。'))

const formatDate = (value) => {
  if (!value) return '未提供'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return String(value)
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(parsed)
}

const generatedAt = computed(() => formatDate(props.report?.generatedAt || rawReport.value.created_at))
const networkRequested = computed(() => decision.value.quality?.network_requested === true)
const networkUsed = computed(() => decision.value.quality?.network_used === true)
const retrievalFailures = computed(() => asCount(decision.value.quality?.retrieval_failures))
const modeLabel = computed(() => ({
  local_ai_style_and_offline_inventory: '本地 AI 写作风格分析',
  local_ai_style: '本地 AI 写作风格分析',
  offline_inventory: '离线声明与来源清单',
  online_verification: '联网证据核查'
}[decision.value.mode] || decision.value.mode || '未说明'))

const limitations = computed(() => {
  const items = props.report?.warnings || rawReport.value.limitations
  if (Array.isArray(items) && items.length) return items
  return ['结果仅覆盖本次列出的声明与来源，重要内容仍需人工复核。']
})

const declaredOriginEntries = computed(() => {
  const origin = metadata.value.declared_origin
  if (!origin || typeof origin !== 'object') return []
  return [
    { key: 'url', label: '声明网址', value: origin.url },
    { key: 'author', label: '声明作者', value: origin.author },
    { key: 'published_at', label: '声明发布时间', value: origin.published_at }
  ].filter((item) => item.value)
})

const assessmentLabel = (value) => ({
  supported: '当前范围内获支持',
  contradicted: '发现相反证据',
  mixed: '证据存在冲突',
  insufficient_evidence: '证据不足',
  not_checked: '尚未核验',
  out_of_scope: '不在核查范围',
  unknown: '状态未知'
}[value] || '状态未知')

const assessmentReasonLabel = (value) => ({
  offline_mode: '离线模式，未执行外部核验',
  non_factual_statement: '观点、预测或其他非客观事实内容',
  retrieval_failed: '来源检索或读取未完成',
  evidence_gate_not_met: '可用证据未达到准入要求'
}[value] || value || '未提供说明')

const materialityLabel = (value) => ({
  high: '重要性高',
  medium: '重要性中',
  low: '重要性低'
}[value] || '重要性未标注')

const percentLabel = (value) => {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return `${Math.round((numeric <= 1 ? numeric * 100 : numeric))}%`
}

const segmentSignalLabel = (value) => ({
  high: '强 AI 写作风格信号，仅供实验性复核',
  mixed: '信号位于灰区或与其他段落不一致',
  low: '当前段落未出现强 AI 写作风格信号'
}[value] || '段落信号未分级')

const sourceSpanLabel = (claim) => {
  const span = claim.source_span
  const paragraph = Number.isInteger(claim.paragraph_index)
    ? `第 ${claim.paragraph_index + 1} 段`
    : '段落未标注'
  if (!span || !Number.isFinite(Number(span.start)) || !Number.isFinite(Number(span.end))) {
    return paragraph
  }
  return `${paragraph} · 字符 ${span.start}–${span.end}`
}

const evidenceRelationLabel = (value) => ({
  supports: '支持',
  contradicts: '相反',
  context_only: '仅作背景'
}[value] || '证据线索')

const formatValue = (value) => {
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch {
    return '未提供证据说明'
  }
}

const safeSourceUrl = (source) => {
  const value = source?.canonical_url || source?.raw_url
  if (!value) return ''
  try {
    const parsed = new URL(value)
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : ''
  } catch {
    return ''
  }
}

const sourceStatusLabel = (value) => ({
  not_fetched: '未抓取（仅登记）',
  reachable: '已读取',
  verified: '已验证',
  fetch_failed: '读取失败',
  unreachable: '无法访问',
  unknown: '状态未知'
}[value] || value || '状态未知')

const sourceRoleLabel = (value) => ({
  inline_link: '文内链接',
  declared_origin: '用户声明来源',
  retrieved_source: '核查来源'
}[value] || value || '来源角色未标注')

const sourceClassLabel = (value) => ({
  official_primary: '官方原始材料',
  scholarly_primary: '学术原始材料',
  reputable_secondary: '专业二手来源',
  user_generated: '用户生成内容',
  unknown: '来源类别未知'
}[value] || value || '来源类别未知')

const qualityFlagLabel = (value) => ({
  offline_mode: '离线模式',
  missing_publisher: '缺少发布主体',
  missing_date: '缺少发布日期',
  stale: '可能过期'
}[value] || value)
</script>

<style lang="scss" scoped>
.article-report {
  --module-border: rgba(193, 223, 225, 0.12);
  --module-bg: rgba(255, 255, 255, 0.022);
  width: 100%;
  color: #f2f0e9;
  border: 1px solid rgba(193, 223, 225, 0.15);
  border-radius: 18px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.006)),
    rgba(13, 19, 22, 0.9);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.08),
    0 28px 80px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(24px) saturate(130%);
  overflow: hidden;
}

.report-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 42px;
  padding: 30px;
  border-bottom: 1px solid var(--module-border);
  background:
    radial-gradient(circle at 8% 0%, rgba(111, 184, 184, 0.08), transparent 37%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.008));
}

.status-line,
.claim-identifiers,
.quality-flags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 7px;
}

.priority-badge,
.scope-badge,
.claim-identifiers span,
.assessment-badge,
.source-status > span,
.quality-flags li {
  display: inline-flex;
  align-items: center;
  border-radius: 8px;
  font-size: 0.72rem;
  font-weight: 800;
}

.priority-badge,
.scope-badge {
  min-height: 28px;
  padding: 0 9px;
}

.priority-badge {
  color: #f0d68d;
  border: 1px solid #8c7846;
  background: #272219;
}

.priority-high .priority-badge {
  color: #f0aaa4;
  border-color: #75423e;
  background: #281918;
}

.priority-low .priority-badge {
  color: #9bd4c7;
  border-color: #41736e;
  background: #172724;
}

.scope-badge {
  color: #91c9c6;
  border: 1px solid rgba(134, 194, 192, 0.14);
  background: rgba(89, 151, 150, 0.09);
}

.verdict-copy h2 {
  margin: 18px 0 8px;
  font-size: 2rem;
  line-height: 1.2;
}

.summary {
  max-width: 760px;
  margin: 0;
  color: #b1b8b6;
  font-size: 0.94rem;
  line-height: 1.7;
}

.next-action {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr);
  gap: 12px;
  margin-top: 20px;
  padding: 14px 15px;
  border: 1px solid var(--module-border);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.015);
}

.next-action span {
  color: #d9bb69;
  font-size: 0.78rem;
  font-weight: 900;
}

.next-action p {
  margin: 0;
  color: #c5cbc8;
  font-size: 0.86rem;
  line-height: 1.6;
}

.header-facts {
  align-self: stretch;
  display: grid;
  align-content: center;
  margin: 0;
  padding: 11px 16px;
  border: 1px solid var(--module-border);
  border-radius: 14px;
  background: rgba(4, 11, 14, 0.2);
}

.header-facts div {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding: 11px 0;
  border-bottom: 1px solid rgba(193, 223, 225, 0.09);
}

.header-facts div:last-child {
  border-bottom: 0;
}

.header-facts dt {
  color: #7f8988;
  font-size: 0.78rem;
}

.header-facts dd {
  margin: 0;
  color: #e7e5de;
  font-size: 0.8rem;
  font-weight: 800;
  text-align: right;
}

.report-body {
  display: grid;
  gap: 14px;
  padding: 26px;
}

.panel,
.details-panel {
  border: 1px solid var(--module-border);
  border-radius: 14px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.024), rgba(255, 255, 255, 0.004)),
    rgba(3, 9, 11, 0.16);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
}

.panel {
  padding: 20px;
}

.section-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
}

.section-heading span {
  color: #6fb8b8;
  font-size: 0.69rem;
  font-weight: 900;
  letter-spacing: 0.12em;
}

.section-heading h3 {
  margin: 3px 0 0;
  font-size: 1.04rem;
}

.section-heading small {
  color: #788281;
  font-size: 0.72rem;
  text-align: right;
}

.coverage-progress {
  margin-top: 20px;
}

.coverage-progress > div:first-child {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  color: #aab2b0;
  font-size: 0.8rem;
}

.coverage-progress strong {
  color: #e6e3dc;
}

.progress-track {
  height: 7px;
  margin-top: 8px;
  border-radius: 999px;
  background: rgba(176, 207, 210, 0.12);
  overflow: hidden;
}

.progress-track span {
  height: 100%;
  display: block;
  border-radius: inherit;
  background: linear-gradient(90deg, #4e9995, #7bc6bf);
}

.coverage-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 9px;
  margin: 18px 0 0;
}

.coverage-grid div {
  min-width: 0;
  padding: 12px;
  border: 1px solid rgba(193, 223, 225, 0.08);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.012);
}

.coverage-grid dt {
  color: #7e8987;
  font-size: 0.7rem;
}

.coverage-grid dd {
  margin: 6px 0 0;
  color: #e5e3dc;
  font-size: 1.12rem;
  font-weight: 900;
}

.claim-list,
.source-list,
.evidence-links ul,
.missing-evidence ul,
.quality-flags,
.limitations ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

.claim-list,
.source-list {
  display: grid;
  gap: 10px;
  margin-top: 16px;
}

.claim-card {
  position: relative;
  padding: 16px;
  border: 1px solid rgba(193, 223, 225, 0.09);
  border-left: 3px solid #7a8785;
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.012);
}

.claim-card.assessment-supported {
  border-left-color: #62afa7;
}

.claim-card.assessment-contradicted,
.claim-card.assessment-mixed {
  border-left-color: #d16e64;
}

.claim-card.assessment-insufficient_evidence,
.claim-card.assessment-not_checked {
  border-left-color: #c8a95b;
}

.claim-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.claim-identifiers span {
  padding: 4px 7px;
  color: #819592;
  border: 1px solid rgba(193, 223, 225, 0.07);
  background: rgba(137, 178, 178, 0.06);
}

.assessment-badge {
  flex: 0 0 auto;
  padding: 5px 8px;
  color: #d7bc6e;
  border: 1px solid rgba(215, 188, 110, 0.18);
  background: rgba(181, 151, 75, 0.09);
}

.assessment-supported .assessment-badge {
  color: #91d0c5;
  border-color: rgba(98, 175, 167, 0.22);
  background: rgba(78, 153, 149, 0.1);
}

.assessment-contradicted .assessment-badge,
.assessment-mixed .assessment-badge {
  color: #efa49d;
  border-color: rgba(209, 110, 100, 0.22);
  background: rgba(171, 74, 66, 0.11);
}

blockquote {
  margin: 15px 0;
  padding: 13px 15px;
  border: 0;
  border-radius: 9px;
  color: #d9ddda;
  background: rgba(2, 7, 9, 0.33);
  font-size: 0.88rem;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.claim-meta,
.source-meta,
.technical-grid {
  margin: 0;
}

.claim-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.claim-meta div,
.source-meta div,
.technical-grid div {
  min-width: 0;
}

.claim-meta dt,
.source-meta dt,
.technical-grid dt {
  color: #75817f;
  font-size: 0.68rem;
}

.claim-meta dd,
.source-meta dd,
.technical-grid dd {
  margin: 4px 0 0;
  color: #acb5b2;
  font-size: 0.75rem;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.evidence-links,
.missing-evidence {
  margin-top: 14px;
}

.evidence-links h4,
.missing-evidence h4,
.details-content h4 {
  margin: 0 0 8px;
  color: #d4d8d5;
  font-size: 0.78rem;
}

.evidence-links li,
.missing-evidence li,
.limitations li {
  position: relative;
  padding: 4px 0 4px 14px;
  color: #929c9a;
  font-size: 0.75rem;
  line-height: 1.6;
}

.evidence-links li::before,
.missing-evidence li::before,
.limitations li::before {
  content: '';
  width: 4px;
  height: 4px;
  position: absolute;
  top: 12px;
  left: 0;
  border-radius: 50%;
  background: #b59b55;
}

.evidence-links strong {
  margin-right: 8px;
  color: #a9c7c3;
}

.source-list > li {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(180px, 0.7fr);
  gap: 12px 24px;
  padding: 15px;
  border: 1px solid rgba(193, 223, 225, 0.09);
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.012);
}

.source-main {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: start;
  gap: 11px;
}

.source-id {
  padding: 4px 7px;
  border-radius: 7px;
  color: #7fc0bd;
  background: rgba(89, 151, 150, 0.09);
  font-size: 0.68rem;
  font-weight: 900;
}

.source-main a,
.source-main strong {
  display: block;
  color: #dce0dc;
  font-size: 0.84rem;
  overflow-wrap: anywhere;
}

.source-main a:hover {
  color: #8fd0ca;
}

.source-main p {
  margin: 4px 0 0;
  color: #7d8987;
  font-size: 0.72rem;
}

.source-status {
  display: grid;
  justify-items: end;
  align-content: start;
  gap: 5px;
  text-align: right;
}

.source-status > span {
  padding: 5px 8px;
  color: #9ed0cb;
  border: 1px solid rgba(98, 175, 167, 0.18);
  background: rgba(78, 153, 149, 0.08);
}

.source-status .status-not_fetched,
.source-status .status-fetch_failed,
.source-status .status-unreachable {
  color: #dfc176;
  border-color: rgba(202, 171, 92, 0.2);
  background: rgba(181, 151, 75, 0.08);
}

.source-status small {
  color: #75807e;
  font-size: 0.68rem;
}

.source-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.quality-flags {
  justify-content: flex-end;
}

.quality-flags li {
  padding: 4px 7px;
  color: #899795;
  border: 1px solid rgba(193, 223, 225, 0.07);
}

.empty-state {
  display: grid;
  gap: 5px;
  margin-top: 16px;
  padding: 20px;
  border: 1px dashed rgba(193, 223, 225, 0.12);
  border-radius: 10px;
  color: #7f8a88;
  text-align: center;
}

.empty-state strong {
  color: #adb6b3;
  font-size: 0.84rem;
}

.empty-state p {
  margin: 0;
  font-size: 0.75rem;
  line-height: 1.6;
}

.details-panel {
  padding: 0 18px;
}

.details-panel summary {
  min-height: 66px;
  cursor: pointer;
}

.details-panel summary > div {
  display: inline-grid;
  gap: 2px;
  margin-left: 6px;
  vertical-align: middle;
}

.details-panel summary strong {
  color: #d9ddda;
  font-size: 0.86rem;
}

.details-panel summary span {
  color: #778180;
  font-size: 0.72rem;
}

.details-content {
  display: grid;
  gap: 22px;
  padding: 3px 0 20px;
}

.details-content section {
  padding-top: 18px;
  border-top: 1px solid rgba(193, 223, 225, 0.1);
}

.technical-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 24px;
}

.technical-grid div {
  padding: 8px 0;
  border-bottom: 1px solid rgba(193, 223, 225, 0.08);
}

.origin-note {
  margin: 12px 0 0;
  color: #b8a66f;
  font-size: 0.73rem;
}

footer {
  min-height: 50px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 0 26px;
  border-top: 1px solid var(--module-border);
  color: #6f7978;
  background: rgba(255, 255, 255, 0.008);
  font-size: 0.7rem;
}

footer span {
  max-width: 360px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

footer p {
  margin: 0;
  text-align: right;
}

@media (max-width: 900px) {
  .report-header {
    grid-template-columns: 1fr;
    gap: 22px;
  }

  .coverage-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .report-header,
  .report-body {
    padding: 18px;
  }

  .verdict-copy h2 {
    font-size: 1.55rem;
  }

  .next-action,
  .claim-meta,
  .technical-grid {
    grid-template-columns: 1fr;
  }

  .section-heading,
  .claim-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .section-heading small {
    text-align: left;
  }

  .coverage-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .source-list > li {
    grid-template-columns: 1fr;
  }

  .source-status {
    justify-items: start;
    text-align: left;
  }

  .quality-flags {
    justify-content: flex-start;
  }

  footer {
    align-items: flex-start;
    flex-direction: column;
    padding: 14px 18px;
  }

  footer p {
    text-align: left;
  }
}

/* Result experience refresh: low-luminance navy + progressive disclosure. */
.article-report {
  --module-border: rgba(120, 158, 185, 0.13);
  --module-bg: rgba(18, 40, 60, 0.28);
  color: #e2eaf0;
  border-color: rgba(118, 157, 186, 0.16);
  background:
    radial-gradient(circle at 8% 0%, rgba(66, 115, 150, 0.08), transparent 34%),
    radial-gradient(circle at 92% 12%, rgba(66, 126, 157, 0.035), transparent 28%),
    linear-gradient(145deg, rgba(11, 28, 45, 0.98), rgba(7, 18, 31, 0.99));
  box-shadow:
    inset 0 1px 0 rgba(202, 221, 235, 0.06),
    0 30px 90px rgba(1, 7, 16, 0.3);
}

.report-header {
  grid-template-columns: minmax(0, 1fr) 310px;
  gap: 48px;
  padding: 36px;
  border-bottom-color: rgba(120, 158, 185, 0.12);
  background:
    linear-gradient(110deg, rgba(55, 100, 134, 0.08), transparent 52%),
    rgba(7, 22, 37, 0.34);
}

.verdict-copy h2 {
  margin-top: 16px;
  color: #e8eef2;
  font-size: clamp(1.85rem, 3vw, 2.45rem);
  font-weight: 760;
  letter-spacing: -0.025em;
}

.summary {
  max-width: 720px;
  color: rgba(197, 211, 221, 0.68);
}

.priority-badge {
  color: #ffdc92;
  border-color: rgba(255, 201, 105, 0.34);
  background: rgba(156, 103, 25, 0.2);
}

.priority-high .priority-badge {
  color: #ffb1b5;
  border-color: rgba(255, 112, 119, 0.38);
  background: rgba(150, 39, 54, 0.23);
}

.priority-low .priority-badge {
  color: #9bead6;
  border-color: rgba(86, 221, 193, 0.32);
  background: rgba(24, 131, 114, 0.2);
}

.scope-badge {
  color: #88b6ce;
  border-color: rgba(101, 158, 193, 0.16);
  background: rgba(42, 88, 119, 0.2);
}

.next-action {
  max-width: 820px;
  border-color: rgba(112, 156, 187, 0.13);
  background: rgba(40, 77, 104, 0.14);
}

.next-action span {
  color: #78abc6;
}

.next-action p {
  color: rgba(204, 216, 225, 0.74);
}

.header-facts {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-content: stretch;
  gap: 8px;
  padding: 8px;
  border-color: rgba(120, 158, 185, 0.14);
  background: rgba(6, 20, 34, 0.52);
}

.header-facts div {
  min-width: 0;
  display: grid;
  align-content: center;
  gap: 4px;
  padding: 13px;
  border: 1px solid rgba(120, 158, 185, 0.09);
  border-radius: 10px;
  background: rgba(43, 80, 107, 0.1);
}

.header-facts div:first-child {
  grid-column: 1 / -1;
  padding: 18px 14px;
  background: linear-gradient(135deg, rgba(52, 105, 141, 0.2), rgba(27, 59, 83, 0.13));
}

.header-facts div:last-child {
  border-bottom: 1px solid rgba(120, 158, 185, 0.09);
}

.header-facts dt {
  color: rgba(173, 194, 209, 0.53);
  font-size: 0.72rem;
}

.header-facts dd {
  color: #e1e9ee;
  text-align: left;
}

.header-facts div:first-child dd {
  color: #86b7cf;
  font-size: 1.85rem;
  line-height: 1.05;
}

.report-body {
  gap: 14px;
  padding: 28px;
}

.panel,
.details-panel {
  border-color: rgba(120, 158, 185, 0.12);
  background:
    linear-gradient(145deg, rgba(71, 113, 143, 0.05), transparent),
    rgba(9, 28, 46, 0.52);
}

.panel {
  padding: 22px;
}

.section-heading span {
  color: #6fa8c7;
}

.section-heading h3,
.claim-card blockquote,
.source-main a,
.source-main strong {
  color: #e1e9ee;
}

.section-heading small {
  color: rgba(176, 196, 211, 0.53);
}

.snapshot-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) repeat(2, minmax(180px, 0.75fr));
  gap: 12px;
  margin-top: 18px;
}

.snapshot-grid > div {
  min-width: 0;
  min-height: 118px;
  display: grid;
  align-content: center;
  gap: 6px;
  padding: 18px;
  border: 1px solid rgba(120, 158, 185, 0.1);
  border-radius: 12px;
  background: rgba(39, 74, 100, 0.11);
}

.snapshot-grid span {
  color: rgba(177, 198, 213, 0.59);
  font-size: 0.75rem;
  font-weight: 760;
}

.snapshot-grid strong {
  color: #dfe8ed;
  font-size: 1.75rem;
  line-height: 1;
}

.snapshot-grid small {
  color: rgba(165, 186, 202, 0.48);
  font-size: 0.69rem;
}

.snapshot-primary {
  background:
    linear-gradient(135deg, rgba(52, 105, 141, 0.19), rgba(27, 59, 83, 0.1)) !important;
}

.snapshot-primary strong {
  color: #86b7cf;
  font-size: 2.2rem;
}

.snapshot-primary .progress-track {
  width: min(360px, 100%);
  margin-top: 2px;
  border: 0;
  background: rgba(126, 158, 181, 0.11);
}

.snapshot-primary .progress-track span {
  background: linear-gradient(90deg, #4f86aa, #6aa8c7);
}

.snapshot-metric.metric-alert strong {
  color: #ffabb1;
}

.priority-claim-list {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-items: stretch;
  gap: 10px;
}

.priority-claim-list .claim-card {
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: 16px;
  border-color: rgba(120, 158, 185, 0.1);
  background: rgba(39, 74, 100, 0.11);
}

.claim-card {
  border-color: rgba(120, 158, 185, 0.1);
  background: rgba(39, 74, 100, 0.1);
}

.claim-card.assessment-supported {
  border-left-color: #45d0be;
}

.claim-card.assessment-contradicted,
.claim-card.assessment-mixed {
  border-left-color: #ff7680;
}

.claim-card.assessment-insufficient_evidence,
.claim-card.assessment-not_checked {
  border-left-color: #f3bf62;
}

.claim-identifiers span {
  color: #9abdd0;
  border-color: rgba(120, 158, 185, 0.09);
  background: rgba(44, 83, 109, 0.13);
}

.assessment-badge {
  color: #ffda8a;
  border-color: rgba(243, 191, 98, 0.22);
  background: rgba(170, 110, 31, 0.15);
}

.assessment-supported .assessment-badge {
  color: #9bead6;
  border-color: rgba(69, 208, 190, 0.25);
  background: rgba(24, 131, 114, 0.16);
}

.assessment-contradicted .assessment-badge,
.assessment-mixed .assessment-badge {
  color: #ffb1b5;
  border-color: rgba(255, 118, 128, 0.26);
  background: rgba(150, 39, 54, 0.2);
}

blockquote {
  border: 1px solid rgba(120, 158, 185, 0.07);
  background: rgba(6, 20, 34, 0.44);
}

.priority-claim-list blockquote {
  flex: 1;
  margin: 14px 0 10px;
  padding: 0;
  border: 0;
  background: transparent;
  font-size: 0.84rem;
  line-height: 1.7;
}

.claim-reason {
  margin: 0;
  padding-top: 10px;
  border-top: 1px solid rgba(120, 158, 185, 0.08);
  color: rgba(172, 193, 208, 0.54);
  font-size: 0.72rem;
  line-height: 1.55;
}

.report-details {
  padding: 0 20px;
}

.report-details > summary {
  min-height: 68px;
}

.report-details > summary strong {
  color: #d8e3e9;
}

.report-details > summary span {
  color: rgba(165, 187, 203, 0.48);
}

.details-content {
  gap: 0;
}

.details-content .detail-section {
  padding: 22px 0;
  border-top-color: rgba(120, 158, 185, 0.1);
}

.details-content .section-heading {
  margin-bottom: 0;
}

.source-list > li {
  border-color: rgba(120, 158, 185, 0.1);
  background: rgba(39, 74, 100, 0.1);
}

.source-id {
  color: #81b1c9;
  background: rgba(44, 83, 109, 0.15);
}

.source-main p,
.source-status small,
.claim-meta dd,
.source-meta dd,
.technical-grid dd,
.limitations li {
  color: rgba(175, 196, 211, 0.56);
}

.source-status > span {
  color: #9bead6;
  border-color: rgba(69, 208, 190, 0.23);
  background: rgba(24, 131, 114, 0.14);
}

.claim-meta dt,
.source-meta dt,
.technical-grid dt {
  color: rgba(159, 181, 198, 0.45);
}

.technical-grid div {
  border-bottom-color: rgba(120, 158, 185, 0.08);
}

footer {
  border-top-color: rgba(120, 158, 185, 0.1);
  color: rgba(157, 179, 195, 0.46);
  background: rgba(3, 14, 25, 0.24);
}

@media (max-width: 900px) {
  .report-header {
    grid-template-columns: 1fr;
  }

  .snapshot-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .snapshot-primary {
    grid-column: 1 / -1;
  }

  .priority-claim-list {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .report-header,
  .report-body {
    padding: 18px;
  }

  .header-facts,
  .snapshot-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .snapshot-grid > div {
    min-height: 104px;
    padding: 14px;
  }

  .report-details {
    padding: 0 16px;
  }
}

/* Desktop one-screen article result summary. */
@media (min-width: 1025px) and (min-height: 720px) {
  .article-report {
    min-height: 0;
    height: 100%;
    display: grid;
    grid-template-rows: auto minmax(0, 1fr) auto;
  }

  .report-header {
    grid-template-columns: minmax(0, 1fr) 260px;
    gap: 24px;
    padding: 18px 22px;
  }

  .priority-badge,
  .scope-badge {
    min-height: 24px;
    font-size: 0.68rem;
  }

  .verdict-copy h2 {
    margin: 9px 0 5px;
    font-size: clamp(1.35rem, 2vw, 1.75rem);
  }

  .summary {
    display: -webkit-box;
    overflow: hidden;
    font-size: 0.8rem;
    line-height: 1.5;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
  }

  .next-action {
    grid-template-columns: 68px minmax(0, 1fr);
    gap: 8px;
    margin-top: 9px;
    padding: 8px 10px;
  }

  .next-action span,
  .next-action p {
    font-size: 0.71rem;
    line-height: 1.45;
  }

  .header-facts {
    gap: 6px;
    padding: 6px;
  }

  .header-facts div,
  .header-facts div:first-child {
    padding: 8px 10px;
  }

  .header-facts div:first-child dd {
    font-size: 1.4rem;
  }

  .header-facts dt,
  .header-facts dd {
    font-size: 0.66rem;
  }

  .report-body {
    min-height: 0;
    grid-template-columns: minmax(330px, 0.78fr) minmax(0, 1.45fr);
    grid-template-rows: auto auto;
    align-content: start;
    gap: 8px;
    padding: 12px 14px 8px;
    overflow: hidden;
  }

  .coverage-panel,
  .claims-panel {
    min-height: 0;
    padding: 14px;
    overflow: hidden;
  }

  .coverage-panel {
    grid-column: 1;
  }

  .claims-panel {
    grid-column: 2;
  }

  .section-heading {
    min-height: 34px;
  }

  .section-heading h3 {
    font-size: 0.92rem;
  }

  .section-heading span {
    font-size: 0.63rem;
  }

  .section-heading small {
    max-width: 220px;
    font-size: 0.65rem;
  }

  .snapshot-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 7px;
    margin-top: 9px;
  }

  .snapshot-grid > div {
    min-height: 0;
    padding: 11px;
  }

  .snapshot-primary {
    grid-column: 1 / -1;
  }

  .snapshot-grid span {
    font-size: 0.67rem;
  }

  .snapshot-grid strong {
    font-size: 1.4rem;
  }

  .snapshot-primary strong {
    font-size: 1.75rem;
  }

  .snapshot-grid small {
    font-size: 0.62rem;
  }

  .priority-claim-list {
    height: auto;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    margin-top: 8px;
  }

  .priority-claim-list .claim-card {
    min-height: 0;
    padding: 12px;
  }

  .claim-head {
    gap: 8px;
  }

  .claim-identifiers span,
  .assessment-badge {
    font-size: 0.64rem;
  }

  .priority-claim-list blockquote {
    display: -webkit-box;
    margin: 9px 0 7px;
    overflow: hidden;
    font-size: 0.76rem;
    line-height: 1.55;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 4;
  }

  .claim-reason {
    padding-top: 7px;
    font-size: 0.65rem;
  }

  .report-details {
    grid-column: 1 / -1;
    padding: 0 14px;
  }

  .report-details > summary {
    min-height: 42px;
  }

  .report-details > summary strong {
    font-size: 0.75rem;
  }

  .report-details > summary span {
    font-size: 0.65rem;
  }

  footer {
    min-height: 30px;
    padding: 0 18px;
    font-size: 0.62rem;
  }
}

.text-signal-list .claim-card {
  border-color: rgba(116, 177, 218, 0.14);
}

.text-signal-list .claim-card.signal-high,
.segment-detail-list li.signal-high {
  border-color: rgba(255, 122, 122, 0.26);
  background: rgba(255, 112, 112, 0.055);
}

.text-signal-list .claim-card.signal-low,
.segment-detail-list li.signal-low {
  border-color: rgba(110, 218, 206, 0.2);
  background: rgba(83, 196, 185, 0.045);
}

.assessment-badge.signal-high {
  color: #ffc1c1;
  background: rgba(255, 112, 112, 0.12);
}

.assessment-badge.signal-low {
  color: #a9ece3;
  background: rgba(83, 196, 185, 0.1);
}

.segment-detail-list {
  display: grid;
  gap: 9px;
  margin: 14px 0 0;
  padding: 0;
  list-style: none;
}

.segment-detail-list li {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px 16px;
  padding: 13px 15px;
  border: 1px solid rgba(123, 168, 199, 0.12);
  border-radius: 10px;
  background: rgba(8, 24, 37, 0.52);
}

.segment-detail-list li > div {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.segment-detail-list li > div span {
  color: rgba(188, 208, 220, 0.56);
  font-size: 0.7rem;
}

.segment-detail-list p {
  grid-column: 1;
  margin: 0;
  color: rgba(226, 235, 240, 0.76);
  font-size: 0.8rem;
  line-height: 1.65;
}

.segment-detail-list b {
  grid-column: 2;
  grid-row: 1 / span 2;
  align-self: center;
  color: #eef8ff;
  font-size: 1rem;
}

@media (max-width: 640px) {
  .segment-detail-list li {
    grid-template-columns: 1fr;
  }

  .segment-detail-list p,
  .segment-detail-list b {
    grid-column: 1;
    grid-row: auto;
  }
}

/* Essential report: conclusion, signal, action and two text findings only. */
.article-report.essential-report {
  min-height: 0;
  height: auto;
  display: flex;
  flex-direction: column;
  color: #e5edf2;
  border-color: rgba(124, 162, 190, 0.16);
  border-radius: 18px;
  background:
    radial-gradient(circle at 6% 0%, rgba(72, 121, 155, 0.08), transparent 32%),
    linear-gradient(145deg, rgba(11, 28, 45, 0.99), rgba(7, 18, 31, 0.99));
  box-shadow:
    inset 0 1px 0 rgba(202, 221, 235, 0.055),
    0 28px 80px rgba(1, 7, 16, 0.26);
  overflow: hidden;
}

.essential-header {
  padding: 34px 38px 28px;
  border-bottom: 1px solid rgba(120, 158, 185, 0.1);
}

.essential-header .status-line {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.essential-header h2 {
  margin: 18px 0 10px;
  color: #f0f4f7;
  font-size: clamp(1.9rem, 3vw, 2.5rem);
  font-weight: 780;
  line-height: 1.2;
  letter-spacing: -0.025em;
}

.essential-header > p {
  max-width: 760px;
  margin: 0;
  color: rgba(200, 213, 222, 0.72);
  font-size: 1.08rem;
  line-height: 1.75;
}

.essential-core {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 16px;
  padding: 24px 38px;
  border-bottom: 1px solid rgba(120, 158, 185, 0.1);
}

.essential-signal,
.essential-action {
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 20px;
  border: 1px solid rgba(120, 158, 185, 0.11);
  border-radius: 13px;
  background: rgba(20, 48, 70, 0.28);
}

.essential-signal > span,
.essential-action > span,
.essential-section-heading > div > span {
  color: #74a9c6;
  font-size: 0.76rem;
  font-weight: 850;
  letter-spacing: 0.08em;
}

.essential-signal strong {
  margin: 8px 0 6px;
  color: #adc8d7;
  font-size: 2.8rem;
  line-height: 1;
}

.essential-signal strong.risk-percent {
  color: #ff727d;
  text-shadow: 0 0 18px rgba(255, 82, 96, 0.18);
}

.essential-signal small {
  color: rgba(164, 185, 200, 0.54);
  font-size: 0.72rem;
  line-height: 1.5;
}

.essential-action p {
  margin: 10px 0 0;
  color: rgba(219, 228, 234, 0.84);
  font-size: 1rem;
  line-height: 1.7;
}

.essential-findings {
  min-height: 0;
  flex: 1 1 auto;
  padding: 28px 38px 30px;
}

.essential-section-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
}

.essential-section-heading h3 {
  margin: 5px 0 0;
  color: #e8eef2;
  font-size: 1.25rem;
}

.essential-section-heading > small {
  color: rgba(166, 187, 202, 0.52);
  font-size: 0.78rem;
}

.essential-findings ol {
  display: grid;
  gap: 10px;
  margin: 18px 0 0;
  padding: 0;
  list-style: none;
}

.essential-findings li {
  min-width: 0;
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 14px;
  padding: 16px 18px;
  border: 1px solid rgba(120, 158, 185, 0.1);
  border-radius: 12px;
  background: rgba(27, 58, 80, 0.2);
}

.finding-index {
  color: #6fa8c7;
  font-size: 0.84rem;
  font-weight: 850;
  letter-spacing: 0.08em;
}

.essential-findings li strong {
  color: #e9eff3;
  font-size: 1.12rem;
  line-height: 1.45;
}

.essential-findings li p {
  display: -webkit-box;
  margin: 5px 0 0;
  color: rgba(188, 205, 216, 0.66);
  overflow: hidden;
  font-size: 0.98rem;
  line-height: 1.65;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.essential-empty {
  margin: 18px 0 0;
  padding: 18px;
  color: rgba(188, 205, 216, 0.66);
  border: 1px solid rgba(120, 158, 185, 0.1);
  border-radius: 12px;
  background: rgba(27, 58, 80, 0.16);
  font-size: 0.92rem;
}

.essential-report .essential-footer {
  min-height: 0;
  display: block;
  padding: 15px 38px;
  border-top: 1px solid rgba(120, 158, 185, 0.09);
  color: rgba(154, 176, 192, 0.48);
  background: rgba(3, 14, 25, 0.22);
  font-size: 0.72rem;
}

.essential-report .essential-footer p {
  margin: 0;
}

@media (min-width: 1025px) and (max-height: 940px) {
  .essential-header {
    padding: 18px 32px 16px;
  }

  .essential-header h2 {
    margin: 10px 0 6px;
    font-size: 2rem;
  }

  .essential-header > p {
    font-size: 1rem;
    line-height: 1.55;
  }

  .essential-core {
    gap: 12px;
    padding: 14px 32px;
  }

  .essential-signal,
  .essential-action {
    padding: 13px 16px;
  }

  .essential-signal strong {
    font-size: 2.35rem;
  }

  .essential-action p {
    margin-top: 6px;
    line-height: 1.55;
  }

  .essential-findings {
    padding: 16px 32px 18px;
  }

  .essential-section-heading h3 {
    font-size: 1.18rem;
  }

  .essential-findings ol {
    gap: 8px;
    margin-top: 10px;
  }

  .essential-findings li {
    padding: 10px 14px;
  }

  .essential-findings li p {
    margin-top: 3px;
    line-height: 1.5;
  }

  .essential-report .essential-footer {
    padding: 10px 32px;
  }
}

@media (min-width: 1025px) and (max-height: 700px) {
  .essential-header {
    padding: 12px 24px 10px;
  }

  .essential-header h2 {
    margin: 6px 0 4px;
    font-size: 1.65rem;
  }

  .essential-header > p {
    display: -webkit-box;
    overflow: hidden;
    line-height: 1.35;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 1;
  }

  .essential-core {
    grid-template-columns: 190px minmax(0, 1fr);
    gap: 8px;
    padding: 9px 24px;
  }

  .essential-signal,
  .essential-action {
    padding: 9px 12px;
  }

  .essential-signal strong {
    margin: 5px 0 3px;
    font-size: 2rem;
  }

  .essential-signal small {
    line-height: 1.25;
  }

  .essential-action p {
    margin-top: 4px;
    line-height: 1.35;
  }

  .essential-findings {
    padding: 10px 24px 12px;
  }

  .essential-section-heading h3 {
    margin-top: 2px;
    font-size: 1.05rem;
  }

  .essential-findings ol {
    gap: 6px;
    margin-top: 7px;
  }

  .essential-findings li {
    grid-template-columns: 34px minmax(0, 1fr);
    gap: 9px;
    padding: 7px 11px;
  }

  .essential-findings li strong {
    font-size: 0.98rem;
  }

  .essential-findings li p {
    margin-top: 1px;
    line-height: 1.35;
    -webkit-line-clamp: 1;
  }

  .essential-report .essential-footer {
    padding: 7px 24px;
  }
}

@media (max-width: 720px) {
  .essential-header,
  .essential-findings {
    padding: 24px 20px;
  }

  .essential-header h2 {
    font-size: 1.65rem;
  }

  .essential-header > p {
    font-size: 0.92rem;
  }

  .essential-core {
    grid-template-columns: 1fr;
    padding: 18px 20px;
  }

  .essential-signal strong {
    font-size: 2.35rem;
  }

  .essential-report .essential-footer {
    padding: 14px 20px;
  }
}
</style>
