<template>
  <article v-if="report" class="report essential-report" :class="`risk-${riskLevel}`">
    <header class="essential-header">
      <div class="status-line">
        <span class="risk-badge">{{ riskLabel }}</span>
        <span class="engine-label">{{ engineLabel }}</span>
      </div>
      <h2>{{ conclusion }}</h2>
      <p>{{ summary }}</p>
    </header>

    <div class="essential-body">
      <div class="essential-text">
        <div class="essential-core">
          <section class="essential-signal">
            <span>{{ isVideo ? '可疑片段信号' : 'AI 生成信号' }}</span>
            <strong :class="{ 'risk-percent': showFinalConfidence }">
              {{ showFinalConfidence ? `${Math.round(confidenceValue)}%` : '未给出' }}
            </strong>
            <small>模型信号用于风险分流，不代表事实概率</small>
          </section>

          <section class="essential-action">
            <span>建议处理</span>
            <p>{{ recommendation }}</p>
          </section>
        </div>

        <section class="essential-findings">
          <div class="essential-section-heading">
            <div>
              <span>核心依据</span>
              <h3>为什么得到这个结果</h3>
            </div>
            <small>{{ primaryEvidence.length }} 项</small>
          </div>

          <ol v-if="primaryEvidence.length">
            <li v-for="(item, index) in primaryEvidence" :key="item.id">
              <span class="finding-index">{{ String(index + 1).padStart(2, '0') }}</span>
              <div>
                <strong>{{ item.title }}</strong>
                <p>{{ item.description }}</p>
              </div>
            </li>
          </ol>
          <p v-else class="essential-empty">本次没有足够的关键依据，请保留“无法确认”的结论。</p>
        </section>
      </div>

      <aside class="essential-media" aria-label="本次检测素材">
        <div class="essential-media-heading">
          <div>
            <span>检测对象</span>
            <strong>{{ isVideo ? '上传视频' : '上传图片' }}</strong>
          </div>
          <small>{{ isVideo ? 'VIDEO' : 'IMAGE' }}</small>
        </div>

        <figure class="essential-media-frame" :class="{ 'is-video': isVideo }">
          <video
            v-if="isVideo && reportPreviewUrl"
            :src="reportPreviewUrl"
            controls
            playsinline
            preload="metadata"
          />
          <img
            v-else-if="!isVideo && reportPreviewUrl"
            :src="reportPreviewUrl"
            :alt="inputName"
          />
          <div v-else class="essential-media-empty">本次报告未保留素材预览</div>
        </figure>

        <div
          v-if="isVideo && (timelineSegments.length || previewKeyFrames.length)"
          class="essential-video-timeline"
        >
          <div class="essential-video-timeline-heading">
            <span>可疑帧时间轴</span>
            <small>0:00 — {{ formatTimelineTime(videoDuration) }}</small>
          </div>
          <div class="essential-video-track" aria-label="视频可疑帧时间轴">
            <span
              v-for="(segment, index) in timelineSegments"
              :key="segment.id || `risk-segment-${index}`"
              class="essential-risk-range"
              :style="timelineSegmentStyle(segment)"
            ></span>
            <i
              v-for="(frame, index) in previewKeyFrames"
              :key="frame.id || `frame-marker-${index}`"
              class="essential-frame-marker"
              :style="timelineMarkerStyle(frame)"
            ></i>
          </div>
        </div>

        <div v-if="isVideo && previewKeyFrames.length" class="essential-frame-strip">
          <div class="essential-frame-strip-heading">
            <span>代表帧</span>
            <small>{{ previewKeyFrames.length }} 帧</small>
          </div>
          <div class="essential-frame-grid">
            <figure
              v-for="(frame, index) in previewKeyFrames"
              :key="frame.id || frame.timestamp || `preview-frame-${index}`"
            >
              <img :src="framePreviewUrl(frame)" :alt="`视频 ${formatTimelineTime(frame.timestamp)} 代表帧`" />
              <figcaption>{{ formatTimelineTime(frame.timestamp) }}</figcaption>
            </figure>
          </div>
        </div>

        <p class="essential-media-name" :title="inputName">{{ inputName }}</p>
      </aside>
    </div>

    <footer class="essential-footer">
      <p>结果仅用于风险辅助判断，不构成司法鉴定或来源证明。</p>
    </footer>
  </article>

  <article v-else-if="false" class="report" :class="`risk-${riskLevel}`">
    <header class="result-overview">
      <div class="verdict-copy">
        <div class="status-line">
          <span class="risk-badge">{{ riskLabel }}</span>
          <span class="engine-label">{{ engineLabel }}</span>
        </div>
        <h2>{{ conclusion }}</h2>
        <p class="summary">{{ summary }}</p>
        <div class="recommendation">
          <span>建议处理</span>
          <p>{{ recommendation }}</p>
        </div>
      </div>

      <dl class="result-facts">
        <div class="primary-fact">
          <dt>{{ isVideo ? '可疑片段信号' : 'AI 生成信号' }}</dt>
          <dd :class="{ 'risk-percent': showFinalConfidence }">
            {{ showFinalConfidence ? `${Math.round(confidenceValue)}%` : '未给出' }}
          </dd>
        </div>
        <div>
          <dt>证据冲突</dt>
          <dd>{{ conflictLevelText }}</dd>
        </div>
        <div>
          <dt>关键依据</dt>
          <dd>{{ displayEvidence.length }} 项</dd>
        </div>
      </dl>
    </header>

    <div class="report-layout">
      <div class="evidence-pane">
        <section class="content-section key-evidence">
          <div class="section-title row-title">
            <div>
              <span>KEY FINDINGS</span>
              <h3>优先判断依据</h3>
            </div>
            <small>仅展示最重要的 {{ primaryEvidence.length }} 项</small>
          </div>

          <ol class="evidence-list">
            <li v-for="item in primaryEvidence" :key="item.id">
              <span class="evidence-category">{{ item.category }}</span>
              <div>
                <strong>{{ item.title }}</strong>
                <p>{{ item.description }}</p>
              </div>
              <span v-if="item.modelScore != null" class="evidence-score">{{ item.modelScore }}%</span>
            </li>
            <li v-if="!primaryEvidence.length" class="empty-state">本次没有可用的关键证据。</li>
          </ol>
        </section>

        <section class="content-section evidence-strength">
          <div class="section-title row-title">
            <div>
              <span>EVIDENCE BALANCE</span>
              <h3>证据概览</h3>
            </div>
            <small>表示证据强度，不是真假概率</small>
          </div>

          <div v-if="scorecardItems.length" class="score-list">
            <div v-for="item in scorecardItems" :key="item.key" class="score-item">
              <div>
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}%</strong>
              </div>
              <div class="score-track">
                <span :class="`score-${item.key}`" :style="{ width: `${item.value}%` }"></span>
              </div>
            </div>
          </div>
          <p v-else class="empty-state">本次报告没有可展示的融合评分。</p>
        </section>
      </div>

      <aside class="media-pane">
        <div class="section-title">
          <span>INSPECTION TARGET</span>
          <h3>{{ isVideo ? '关键帧与风险时间轴' : '检测对象' }}</h3>
        </div>

        <figure v-if="!isVideo" class="image-block">
          <img v-if="visualization.imageUrl" :src="visualization.imageUrl" :alt="inputName" />
          <div v-else class="preview-missing">本次报告未保留图片预览</div>
        </figure>

        <div v-else class="video-visualization">
          <div v-if="keyFrames.length" class="key-frame-grid">
            <figure v-for="frame in keyFrames.slice(0, 4)" :key="frame.id || frame.timestamp">
              <img :src="frame.preview" :alt="`视频 ${formatTimelineTime(frame.timestamp)} 关键帧`" />
              <figcaption>{{ formatTimelineTime(frame.timestamp) }}</figcaption>
            </figure>
          </div>
          <div v-else class="video-preview-missing">
            <span>VIDEO</span>
            <p>本次报告未保留关键帧预览</p>
          </div>

          <section class="timeline-card">
            <div>
              <strong>风险时间轴</strong>
              <span>{{ formatTimelineTime(videoDuration) }}</span>
            </div>
            <div class="timeline-track" aria-label="视频风险时间轴">
              <span
                v-for="segment in timelineSegments"
                :key="segment.id"
                :class="`segment-${segment.status}`"
                :style="timelineSegmentStyle(segment)"
                :title="`${formatTimelineTime(segment.start)}–${formatTimelineTime(segment.end)} ${segment.description}`"
              ></span>
            </div>
            <ol v-if="timelineSegments.length" class="timeline-list">
              <li v-for="segment in timelineSegments.slice(0, 2)" :key="segment.id">
                <span :class="`dot-${segment.status}`"></span>
                <time>{{ formatTimelineTime(segment.start) }}–{{ formatTimelineTime(segment.end) }}</time>
                <p>{{ segment.description }}</p>
              </li>
            </ol>
            <p v-else class="timeline-empty">未返回分段风险数据，结论来自关键帧聚合结果。</p>
          </section>
        </div>

        <div class="media-meta">
          <strong :title="inputName">{{ inputName }}</strong>
          <dl>
            <div>
              <dt>格式</dt>
              <dd>{{ quickMetadata.format || '未知' }}</dd>
            </div>
            <div>
              <dt>分辨率</dt>
              <dd>{{ quickMetadata.resolution || '未知' }}</dd>
            </div>
            <div>
              <dt>来源</dt>
              <dd>{{ quickMetadata.source || '自动判断' }}</dd>
            </div>
          </dl>
        </div>
      </aside>
    </div>

    <details class="technical-details">
      <summary>
        <strong>查看完整技术明细</strong>
        <span>全部证据、模型输出、元数据与局限说明</span>
      </summary>

      <div class="technical-content">
        <section v-if="displayEvidence.length">
          <h4>全部判断依据</h4>
          <ol class="evidence-list full-evidence-list">
            <li v-for="item in displayEvidence" :key="item.id">
              <span class="evidence-category">{{ item.category }}</span>
              <div>
                <strong>{{ item.title }}</strong>
                <p>{{ item.description }}</p>
                <ul v-if="item.signals?.length" class="signal-list">
                  <li v-for="signal in item.signals" :key="signal">{{ signal }}</li>
                </ul>
              </div>
              <span v-if="item.modelScore != null" class="evidence-score">AI 信号 {{ item.modelScore }}%</span>
            </li>
          </ol>
        </section>

        <section>
          <h4>模型输出</h4>
          <ul class="model-list">
            <li v-for="model in models" :key="model.model_id || model.modelId">
              <div>
                <strong>{{ model.model_id || model.modelId || 'unknown-model' }}</strong>
                <span>{{ model.model_version || model.modelVersion || 'unknown' }}</span>
              </div>
              <span v-if="model.ai_score != null">AI 信号 {{ formatPercentScore(model.ai_score) }}</span>
              <span v-else-if="model.score != null">分数 {{ formatScore(model.score) }}</span>
              <span v-else>无有效分数</span>
              <p v-if="model.error" class="model-error">{{ model.error }}</p>
            </li>
            <li v-if="!models.length" class="empty-state">未返回模型信息。</li>
          </ul>
        </section>

        <section>
          <h4>完整元数据</h4>
          <dl class="metadata-list">
            <div v-for="item in metadataItems" :key="item.key">
              <dt>{{ item.label }}</dt>
              <dd>{{ item.value }}</dd>
            </div>
          </dl>
        </section>

        <section class="limitations">
          <h4>局限说明</h4>
          <ul>
            <li v-for="warning in warnings" :key="warning">{{ warning }}</li>
          </ul>
        </section>
      </div>
    </details>

    <footer>
      <span>{{ taskId }}</span>
      <p>{{ generatedAt || '刚刚' }} · 该结果用于风险辅助判断，不构成司法鉴定或来源证明。</p>
    </footer>
  </article>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  report: {
    type: Object,
    default: null
  },
  previewUrl: {
    type: String,
    default: ''
  }
})

const rawReport = computed(() => props.report?.raw || props.report || {})
const taskId = computed(() => props.report?.taskId || rawReport.value.task_id || '')
const inputName = computed(() => props.report?.inputName || rawReport.value.metadata?.filename || '图片文件')
const verdict = computed(() => props.report?.verdict || rawReport.value.verdict || '')
const conclusion = computed(() => props.report?.conclusion || ({
  ai_generated: '检测到 AI 生成风险',
  deepfake_suspected: '检测到疑似 Deepfake 风险',
  ai_generated_video_suspected: '检测到完整 AI 生成视频信号',
  face_manipulation_suspected: '检测到人脸换脸或操纵信号',
  multiple_video_ai_signals: '检测到多种视频 AI 伪造信号',
  likely_real: '当前未发现明显 AI 生成风险',
  uncertain: '当前无法确认',
  failed: '检测未完成'
}[verdict.value] || '检测完成'))
const summary = computed(() => props.report?.summary || rawReport.value.summary || '本次检测没有返回结果摘要。')
const riskLevel = computed(() => props.report?.riskLevel || rawReport.value.risk_level || 'unknown')
const riskLabel = computed(() => props.report?.riskLabel || ({
  high: '高风险',
  medium: '中风险',
  low: '低风险',
  unknown: verdict.value === 'failed' ? '检测失败' : '无法确认'
}[riskLevel.value] || '无法确认'))
const recommendation = computed(() => ({
  ai_generated: '将结果作为风险线索处理，保留原始文件与来源信息，重要场景建议人工复核。',
  deepfake_suspected: '将可疑片段作为风险线索处理，保留原始视频并结合来源链进行人工复核。',
  ai_generated_video_suspected: '保留原始视频与生成来源信息，结合采样帧证据人工复核；不要仅凭本报告定性。',
  face_manipulation_suspected: '重点复核人脸区域、原始拍摄链路与未压缩素材，并与完整生成分支分开解释。',
  multiple_video_ai_signals: '两个主分支同时报警，建议优先隔离传播并由人工核验原始素材与来源链。',
  likely_real: '当前可以按低风险处理，但仍应保留原始来源，避免把本报告作为唯一证明。',
  uncertain: '补充原始来源、拍摄上下文或未经平台压缩的原图，重要场景请人工复核。',
  failed: '确认本地模型服务可用后重新检测，本次不应形成真假判断。'
}[verdict.value] || '结合图片原始来源和使用场景进行判断。'))

const confidence = computed(() => props.report?.confidence ?? rawReport.value.confidence)
const confidenceValue = computed(() => {
  if (confidence.value == null) return 0
  const numeric = Number(confidence.value)
  return Math.max(0, Math.min(100, numeric <= 1 ? numeric * 100 : numeric))
})
const showFinalConfidence = computed(() => confidence.value != null && verdict.value !== 'uncertain')
const decision = computed(() => props.report?.decision || rawReport.value.decision || {})
const evidenceScores = computed(() => decision.value.evidence_scores || {})
const scorePercent = (value) => {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return null
  return Math.round(Math.max(0, Math.min(1, numeric)) * 100)
}
const scorecardItems = computed(() => [
  { key: 'ai', label: 'AI 生成证据', value: scorePercent(evidenceScores.value.ai_evidence_strength) },
  { key: 'real', label: '真实来源证据', value: scorePercent(evidenceScores.value.real_evidence_strength) },
  { key: 'source', label: '来源线索完整度', value: scorePercent(evidenceScores.value.provenance_strength) }
].filter((item) => item.value != null))
const conflictLevelText = computed(() => ({ high: '高', medium: '中', low: '低' }[evidenceScores.value.conflict_level] || '未知'))

const evidenceCategory = (item) => {
  const id = String(item.id || '')
  if (id.includes('source') || id.includes('exif')) return '来源'
  if (id.includes('credential') || id.includes('metadata')) return '元数据'
  if (id.includes('auxiliary')) return '辅助模型'
  if (id.includes('model') || id.includes('ai-image-score')) return '主模型'
  return '综合'
}

const evidence = computed(() => props.report?.evidence || (rawReport.value.evidence || []).map((item, index) => ({
  id: item.id || `evidence-${index + 1}`,
  title: item.title || `证据 ${index + 1}`,
  description: item.description || '',
  modelScore: item.model_score == null ? null : Math.round((Number(item.model_score) <= 1 ? Number(item.model_score) * 100 : Number(item.model_score)) * 10) / 10,
  signals: item.signals || []
})))
const displayEvidence = computed(() => evidence.value
  .filter((item) => item.id !== 'evidence-fusion-scorecard')
  .map((item) => ({ ...item, category: evidenceCategory(item) })))
const primaryEvidence = computed(() => displayEvidence.value.slice(0, 2))

const models = computed(() => props.report?.models || rawReport.value.models || [])
const warnings = computed(() => props.report?.warnings || rawReport.value.limitations || [])
const visualization = computed(() => props.report?.visualization || rawReport.value.visualization || { kind: 'none' })
const metadata = computed(() => props.report?.metadata || rawReport.value.metadata || {})
const isVideo = computed(() => props.report?.mediaType === 'video' || rawReport.value.media_type === 'video' || visualization.value.kind === 'timeline')
const reportPreviewUrl = computed(() => (
  props.previewUrl
  || visualization.value.imageUrl
  || visualization.value.image_url
  || visualization.value.videoUrl
  || visualization.value.video_url
  || ''
))
const keyFrames = computed(() => visualization.value.keyFrames || visualization.value.key_frames || [])
const framePreviewUrl = (frame = {}) => (
  frame.preview
  || frame.imageUrl
  || frame.image_url
  || frame.frame_url
  || frame.thumbnail
  || ''
)
const previewKeyFrames = computed(() => keyFrames.value
  .filter((frame) => framePreviewUrl(frame))
  .slice(0, 3))
const timelineSegments = computed(() => visualization.value.segments || visualization.value.timeline || [])
const videoDuration = computed(() => Number(visualization.value.duration || metadata.value.duration || 0))
const formatTimelineTime = (seconds) => {
  const value = Number(seconds)
  if (!Number.isFinite(value) || value < 0) return '0:00'
  const minutes = Math.floor(value / 60)
  const remain = Math.floor(value % 60)
  return `${minutes}:${String(remain).padStart(2, '0')}`
}
const timelineSegmentStyle = (segment) => {
  const duration = Math.max(videoDuration.value, Number(segment.end || 0), 1)
  const start = Math.max(0, Number(segment.start || 0))
  const end = Math.max(start, Number(segment.end ?? segment.start ?? 0))
  return {
    left: `${Math.min(100, (start / duration) * 100)}%`,
    width: `${Math.max(1.5, Math.min(100 - ((start / duration) * 100), ((end - start) / duration) * 100))}%`
  }
}
const timelineMarkerStyle = (frame) => {
  const duration = Math.max(videoDuration.value, 1)
  const timestamp = Math.max(0, Number(frame.timestamp || 0))
  return {
    left: `${Math.min(100, (timestamp / duration) * 100)}%`
  }
}
const engineLabel = computed(() => props.report?.engine?.label || (verdict.value === 'failed' ? '模型未完成调用' : '多证据检测完成'))
const generatedAt = computed(() => {
  const value = props.report?.generatedAt || rawReport.value.created_at
  return value ? new Date(value).toLocaleString() : ''
})

const sourceLabel = (value) => ({
  auto: '自动判断',
  game_capture: '用户声明：游戏画面',
  screen_capture: '用户声明：电脑或网页截图',
  camera_export: '用户声明：相机/手机拍摄',
  unknown: '用户声明：来源不明'
}[value] || String(value || ''))

const quickMetadata = computed(() => ({
  format: String(metadata.value.format || '').toUpperCase(),
  resolution: metadata.value.resolution || (metadata.value.width && metadata.value.height ? `${metadata.value.width} × ${metadata.value.height}` : ''),
  source: sourceLabel(metadata.value.source_hint)
}))

const labels = {
  filename: '文件名',
  file_size_label: '文件大小',
  format: '格式',
  resolution: '分辨率',
  duration: '时长（秒）',
  fps: '帧率',
  total_frames: '总帧数',
  audio_present: '音频轨道',
  color_mode: '色彩模式',
  exif_present: 'EXIF',
  camera_make: '设备厂商',
  camera_model: '设备型号',
  created_time: '创建时间',
  software: '修改软件',
  xmp_present: 'XMP 元数据',
  generator_metadata_detected: '生成来源线索',
  generator_metadata_producers: '内容生产方/工具',
  editing_software_detected: '编辑软件线索',
  editing_software_names: '编辑软件',
  content_credentials_status: '内容凭证状态',
  source_hint: '用户来源声明',
  protected_domain: '域外保护',
  protected_domain_type: '保护类型',
  protected_domain_signals: '域外信号',
  screen_capture_likely: '截图场景',
  screen_capture_signals: '截图线索'
}

const formatMetadataValue = (key, value) => {
  if (['exif_present', 'xmp_present'].includes(key)) return value ? '存在' : '未读取到'
  if (key === 'generator_metadata_detected') return value ? '检测到' : '未检测到'
  if (key === 'editing_software_detected') return value ? '检测到，仅作编辑链路线索' : '未检测到'
  if (key === 'content_credentials_status') return value === 'marker_present_unverified' ? '检测到容器标记，签名未验证' : '未检测到'
  if (key === 'protected_domain') return value ? '已启用保守判断' : '未启用'
  if (key === 'protected_domain_type') return value === 'game_or_screen_capture' ? '游戏/屏幕截图' : String(value)
  if (key === 'screen_capture_likely') return value ? '可能是截图/游戏画面' : '未识别为截图场景'
  if (key === 'source_hint') return sourceLabel(value)
  if (Array.isArray(value)) return value.length ? value.join('；') : '无'
  return String(value)
}

const metadataItems = computed(() => Object.entries(labels)
  .filter(([key]) => metadata.value[key] !== undefined && metadata.value[key] !== null && metadata.value[key] !== '')
  .map(([key, label]) => ({ key, label, value: formatMetadataValue(key, metadata.value[key]) })))

const formatScore = (score) => {
  const numeric = Number(score)
  if (!Number.isFinite(numeric)) return '无'
  return numeric <= 1 ? numeric.toFixed(3) : String(numeric)
}

const formatPercentScore = (score) => {
  const numeric = Number(score)
  if (!Number.isFinite(numeric)) return '无'
  return `${Math.round((numeric <= 1 ? numeric * 100 : numeric) * 10) / 10}%`
}
</script>

<style lang="scss" scoped>
.report {
  --module-border: rgba(193, 223, 225, 0.12);
  --module-highlight: rgba(255, 255, 255, 0.09);
  --module-bg: rgba(255, 255, 255, 0.022);
  width: 100%;
  position: relative;
  color: #f2f0e9;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.006)),
    rgba(13, 19, 22, 0.88);
  border: 1px solid rgba(193, 223, 225, 0.15);
  border-radius: 18px;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.08),
    0 28px 80px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(24px) saturate(130%);
  overflow: hidden;
}

.report::before {
  content: '';
  position: absolute;
  inset: 0 12% auto;
  z-index: 2;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.27), transparent);
  pointer-events: none;
}

.result-overview {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 42px;
  padding: 30px;
  border-bottom: 1px solid var(--module-border);
  background:
    radial-gradient(circle at 8% 0%, rgba(111, 184, 184, 0.07), transparent 37%),
    linear-gradient(145deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.008));
}

.status-line {
  display: flex;
  align-items: center;
  gap: 10px;
}

.risk-badge,
.engine-label {
  min-height: 28px;
  display: inline-flex;
  align-items: center;
  border-radius: 8px;
  padding: 0 9px;
  font-size: 0.74rem;
  font-weight: 900;
}

.risk-badge {
  border: 1px solid #8c7846;
  color: #f0d68d;
  background: #272219;
}

.risk-high .risk-badge {
  border-color: #75423e;
  color: #f0aaa4;
  background: #281918;
}

.risk-low .risk-badge {
  border-color: #41736e;
  color: #9bd4c7;
  background: #172724;
}

.engine-label {
  color: #8fb4b2;
  border: 1px solid rgba(134, 194, 192, 0.1);
  background: rgba(89, 151, 150, 0.08);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
}

.verdict-copy h2 {
  margin: 18px 0 8px;
  font-size: 2rem;
  line-height: 1.2;
  letter-spacing: 0;
}

.summary {
  max-width: 760px;
  color: #b1b8b6;
  font-size: 0.94rem;
  line-height: 1.7;
}

.recommendation {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 12px;
  margin-top: 20px;
  padding: 14px 15px;
  border: 1px solid var(--module-border);
  border-radius: 12px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.025), transparent),
    rgba(255, 255, 255, 0.012);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
}

.recommendation span {
  color: #d9bb69;
  font-size: 0.78rem;
  font-weight: 900;
}

.recommendation p {
  color: #c5cbc8;
  font-size: 0.86rem;
  line-height: 1.6;
}

.result-facts {
  align-self: stretch;
  display: grid;
  align-content: center;
  gap: 0;
  margin: 0;
  padding: 11px 16px;
  border: 1px solid var(--module-border);
  border-radius: 14px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.03), transparent),
    rgba(4, 11, 14, 0.18);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.045);
}

.result-facts div {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding: 11px 0;
  border-bottom: 1px solid rgba(193, 223, 225, 0.09);
}

.result-facts div:last-child {
  border-bottom: 0;
}

.result-facts dt {
  color: #7f8988;
  font-size: 0.78rem;
}

.result-facts dd {
  margin: 0;
  color: #e7e5de;
  font-size: 0.8rem;
  font-weight: 800;
  text-align: right;
}

.report-layout {
  display: grid;
  grid-template-columns: minmax(340px, 0.85fr) minmax(0, 1.35fr);
}

.media-pane,
.evidence-pane {
  min-width: 0;
  padding: 26px;
}

.media-pane {
  border-right: 1px solid var(--module-border);
  background: rgba(3, 8, 10, 0.18);
}

.section-title > span,
.section-title div > span {
  color: #6fb8b8;
  font-size: 0.7rem;
  font-weight: 900;
  letter-spacing: 0.12em;
}

.section-title h3 {
  margin: 3px 0 0;
  font-size: 1.04rem;
  letter-spacing: 0;
}

.row-title {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
}

.row-title small {
  color: #788281;
  font-size: 0.72rem;
  text-align: right;
}

.image-block {
  height: 430px;
  position: relative;
  display: grid;
  place-items: center;
  margin: 18px 0 0;
  border: 1px solid rgba(193, 223, 225, 0.14);
  border-radius: 13px;
  background: rgba(3, 8, 10, 0.52);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.035),
    0 18px 45px rgba(0, 0, 0, 0.18);
  overflow: hidden;
}

.image-block img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  max-width: 100%;
  max-height: 100%;
  display: block;
  object-fit: contain;
  object-position: center;
}

.video-visualization {
  display: grid;
  gap: 12px;
  margin-top: 18px;
}

.key-frame-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
}

.key-frame-grid figure {
  height: 126px;
  position: relative;
  margin: 0;
  border: 1px solid var(--module-border);
  border-radius: 11px;
  background: rgba(3, 8, 10, 0.48);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
  overflow: hidden;
}

.key-frame-grid img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: contain;
  object-position: center;
}

.key-frame-grid figcaption {
  position: absolute;
  right: 6px;
  bottom: 6px;
  padding: 2px 6px;
  border-radius: 4px;
  color: #f7f4ec;
  background: rgba(4, 8, 9, 0.76);
  font-size: 0.66rem;
  font-weight: 800;
}

.video-preview-missing {
  min-height: 180px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 6px;
  border: 1px solid var(--module-border);
  border-radius: 12px;
  color: #7d8786;
  background: var(--module-bg);
}

.video-preview-missing span {
  color: #67afae;
  font-size: 0.72rem;
  font-weight: 900;
  letter-spacing: 0.16em;
}

.video-preview-missing p {
  font-size: 0.78rem;
}

.timeline-card {
  padding: 14px;
  border: 1px solid var(--module-border);
  border-radius: 12px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.026), transparent),
    var(--module-bg);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
}

.timeline-card > div:first-child {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.timeline-card > div:first-child strong {
  font-size: 0.78rem;
}

.timeline-card > div:first-child span {
  color: #7f8a88;
  font-size: 0.7rem;
}

.timeline-track {
  height: 8px;
  position: relative;
  margin-top: 11px;
  border-radius: 999px;
  background: #253033;
  overflow: hidden;
}

.timeline-track > span {
  min-width: 3px;
  position: absolute;
  top: 0;
  bottom: 0;
  border-radius: 999px;
  background: #69b9b6;
}

.timeline-track .segment-suspicious,
.timeline-track .segment-high,
.dot-suspicious,
.dot-high {
  background: #df735f;
}

.timeline-track .segment-warning,
.timeline-track .segment-medium,
.dot-warning,
.dot-medium {
  background: #dfba60;
}

.timeline-list {
  display: grid;
  gap: 7px;
  margin: 13px 0 0;
  padding: 0;
  list-style: none;
}

.timeline-list li {
  display: grid;
  grid-template-columns: auto 66px minmax(0, 1fr);
  align-items: center;
  gap: 7px;
  color: #9ea8a5;
  font-size: 0.68rem;
}

.timeline-list li > span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #69b9b6;
}

.timeline-list time {
  color: #c9cfcc;
  font-variant-numeric: tabular-nums;
}

.timeline-list p {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timeline-empty {
  margin-top: 12px;
  color: #788381;
  font-size: 0.7rem;
  line-height: 1.55;
}

.preview-missing,
.empty-state {
  color: #7d8786;
  font-size: 0.82rem;
}

.media-meta {
  margin-top: 16px;
}

.media-meta > strong {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.88rem;
}

.media-meta dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 14px 0 0;
}

.media-meta dl div {
  min-width: 0;
  padding: 10px;
  border: 1px solid rgba(193, 223, 225, 0.09);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.014);
}

.media-meta dt,
.metadata-list dt {
  color: #74807e;
  font-size: 0.7rem;
}

.media-meta dd {
  margin: 3px 0 0;
  color: #cbd0ce;
  font-size: 0.76rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.evidence-pane {
  display: grid;
  align-content: start;
  gap: 13px;
  background: rgba(255, 255, 255, 0.004);
}

.content-section {
  padding: 18px;
  border: 1px solid var(--module-border);
  border-radius: 14px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.026), rgba(255, 255, 255, 0.005)),
    rgba(3, 9, 11, 0.13);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
}

.score-list {
  display: grid;
  gap: 14px;
  margin-top: 18px;
}

.score-item > div:first-child {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  color: #aab2b0;
  font-size: 0.8rem;
}

.score-item strong {
  color: #e6e3dc;
}

.score-track {
  height: 7px;
  margin-top: 7px;
  border-radius: 4px;
  border: 1px solid rgba(193, 223, 225, 0.055);
  background: rgba(176, 207, 210, 0.12);
  overflow: hidden;
}

.score-track span {
  display: block;
  height: 100%;
}

.score-ai { background: #d7766d; }
.score-real { background: #64b6ad; }
.score-source { background: #d0b45f; }

.evidence-list,
.signal-list,
.model-list,
.limitations ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

.evidence-list {
  display: grid;
  gap: 7px;
  margin-top: 12px;
}

.evidence-list > li {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr) auto;
  gap: 14px;
  padding: 13px;
  border: 1px solid rgba(193, 223, 225, 0.075);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.012);
}

.evidence-list > li:last-child {
  border-bottom: 1px solid rgba(193, 223, 225, 0.075);
}

.evidence-category {
  color: #78bdbc;
  font-size: 0.72rem;
  font-weight: 900;
}

.evidence-list strong {
  display: block;
  color: #e6e4dd;
  font-size: 0.86rem;
}

.evidence-list p {
  margin-top: 4px;
  color: #929c9a;
  font-size: 0.78rem;
  line-height: 1.6;
}

.evidence-score {
  align-self: start;
  color: #d7bc6e;
  font-size: 0.76rem;
  font-weight: 900;
  white-space: nowrap;
}

.signal-list {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 8px;
}

.signal-list li {
  padding: 3px 6px;
  border: 1px solid rgba(193, 223, 225, 0.07);
  border-radius: 6px;
  color: #8fa3a1;
  background: rgba(137, 178, 178, 0.075);
  font-size: 0.68rem;
}

.technical-details {
  padding: 0 16px;
  border: 1px solid var(--module-border);
  border-radius: 14px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.02), transparent),
    rgba(3, 9, 11, 0.13);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.technical-details summary {
  min-height: 66px;
  display: grid;
  align-content: center;
  gap: 2px;
  cursor: pointer;
  list-style-position: inside;
}

.technical-details summary strong {
  color: #d9ddda;
  font-size: 0.86rem;
}

.technical-details summary span {
  color: #778180;
  font-size: 0.72rem;
}

.technical-content {
  display: grid;
  gap: 24px;
  padding: 4px 0 20px;
}

.technical-content section {
  padding-top: 20px;
  border-top: 1px solid #293134;
}

.technical-content h4 {
  margin: 0 0 12px;
  font-size: 0.82rem;
}

.model-list {
  display: grid;
  gap: 9px;
}

.model-list li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px 16px;
  padding: 10px 0;
  border-bottom: 1px solid #293134;
  color: #aeb6b4;
  font-size: 0.74rem;
}

.model-list li > div {
  min-width: 0;
  display: grid;
}

.model-list li > div span {
  color: #707b79;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-error {
  grid-column: 1 / -1;
  color: #e29a94;
}

.metadata-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 24px;
  margin: 0;
}

.metadata-list div {
  min-width: 0;
  padding: 9px 0;
  border-bottom: 1px solid #293134;
}

.metadata-list dd {
  margin: 3px 0 0;
  color: #b9c0be;
  font-size: 0.74rem;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.limitations li {
  position: relative;
  padding: 5px 0 5px 14px;
  color: #929c9a;
  font-size: 0.76rem;
  line-height: 1.6;
}

.limitations li::before {
  content: '';
  width: 4px;
  height: 4px;
  position: absolute;
  top: 13px;
  left: 0;
  border-radius: 50%;
  background: #b59b55;
}

footer {
  min-height: 50px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 0 26px;
  border-top: 1px solid var(--module-border);
  background: rgba(255, 255, 255, 0.008);
  color: #6f7978;
  font-size: 0.7rem;
}

footer span {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: $tablet) {
  .result-overview {
    grid-template-columns: 1fr;
    gap: 24px;
  }

  .result-facts {
    padding: 11px 16px;
    border: 1px solid var(--module-border);
  }

  .report-layout {
    grid-template-columns: 1fr;
  }

  .media-pane {
    border-right: 0;
    border-bottom: 1px solid var(--module-border);
  }
}

@media (max-width: $mobile) {
  .result-overview,
  .media-pane,
  .evidence-pane {
    padding: 18px;
  }

  .verdict-copy h2 {
    font-size: 1.55rem;
  }

  .recommendation {
    grid-template-columns: 1fr;
    gap: 5px;
  }

  .image-block {
    height: 330px;
  }

  .row-title {
    align-items: flex-start;
    flex-direction: column;
    gap: 5px;
  }

  .row-title small {
    text-align: left;
  }

  .evidence-list > li {
    grid-template-columns: 62px minmax(0, 1fr);
  }

  .evidence-score {
    grid-column: 2;
  }

  .metadata-list {
    grid-template-columns: 1fr;
  }

  footer {
    align-items: flex-start;
    flex-direction: column;
    padding: 14px 18px;
  }
}

/* Result experience refresh: low-luminance navy + conclusion-first hierarchy. */
.report {
  --module-border: rgba(120, 158, 185, 0.13);
  --module-highlight: rgba(172, 198, 216, 0.08);
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

.result-overview {
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

.risk-badge {
  border-color: rgba(255, 201, 105, 0.34);
  color: #ffdc92;
  background: rgba(156, 103, 25, 0.2);
}

.risk-high .risk-badge {
  border-color: rgba(255, 112, 119, 0.38);
  color: #ffb1b5;
  background: rgba(150, 39, 54, 0.23);
}

.risk-low .risk-badge {
  border-color: rgba(86, 221, 193, 0.32);
  color: #9bead6;
  background: rgba(24, 131, 114, 0.2);
}

.engine-label {
  color: #88b6ce;
  border-color: rgba(101, 158, 193, 0.16);
  background: rgba(42, 88, 119, 0.2);
}

.recommendation {
  max-width: 820px;
  border-color: rgba(112, 156, 187, 0.13);
  background: rgba(40, 77, 104, 0.14);
}

.recommendation span {
  color: #78abc6;
}

.recommendation p {
  color: rgba(204, 216, 225, 0.74);
}

.result-facts {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-content: stretch;
  gap: 8px;
  padding: 8px;
  border-color: rgba(120, 158, 185, 0.14);
  background: rgba(6, 20, 34, 0.52);
}

.result-facts div {
  min-width: 0;
  display: grid;
  align-content: center;
  gap: 4px;
  padding: 13px;
  border: 1px solid rgba(120, 158, 185, 0.09);
  border-radius: 10px;
  background: rgba(43, 80, 107, 0.1);
}

.result-facts div:last-child {
  border-bottom: 1px solid rgba(120, 158, 185, 0.09);
}

.result-facts .primary-fact {
  grid-column: 1 / -1;
  padding: 18px 14px;
  background:
    linear-gradient(135deg, rgba(52, 105, 141, 0.2), rgba(27, 59, 83, 0.13));
}

.result-facts dt {
  color: rgba(173, 194, 209, 0.53);
  font-size: 0.72rem;
}

.result-facts dd {
  color: #e1e9ee;
  text-align: left;
}

.result-facts .primary-fact dd {
  color: #86b7cf;
  font-size: 2rem;
  line-height: 1.05;
}

.result-facts .primary-fact dd.risk-percent {
  color: #ff727d;
  text-shadow: 0 0 18px rgba(255, 82, 96, 0.18);
}

.report-layout {
  grid-template-columns: minmax(0, 1.22fr) minmax(310px, 0.78fr);
}

.evidence-pane {
  gap: 14px;
  padding: 28px;
  background: rgba(7, 21, 34, 0.24);
}

.media-pane {
  padding: 28px;
  border-right: 0;
  border-left: 1px solid rgba(120, 158, 185, 0.12);
  background: rgba(5, 18, 31, 0.32);
}

.content-section,
.timeline-card,
.technical-details {
  border-color: rgba(120, 158, 185, 0.12);
  background:
    linear-gradient(145deg, rgba(71, 113, 143, 0.05), transparent),
    rgba(9, 28, 46, 0.52);
}

.section-title > span,
.section-title div > span {
  color: #6fa8c7;
}

.section-title h3,
.evidence-list strong {
  color: #e1e9ee;
}

.row-title small,
.evidence-list p,
.timeline-empty {
  color: rgba(176, 196, 211, 0.56);
}

.key-evidence {
  padding: 22px;
}

.evidence-list {
  gap: 9px;
  margin-top: 16px;
}

.evidence-list > li {
  grid-template-columns: 64px minmax(0, 1fr) auto;
  padding: 15px;
  border-color: rgba(120, 158, 185, 0.1);
  background: rgba(39, 74, 100, 0.11);
}

.evidence-category {
  color: #73a9c5;
}

.evidence-score {
  min-width: 48px;
  padding: 4px 8px;
  border-radius: 999px;
  color: #bdd3df;
  background: rgba(52, 99, 130, 0.17);
  text-align: center;
}

.evidence-strength {
  padding: 18px 22px;
}

.score-list {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
  margin-top: 16px;
}

.score-item > div:first-child {
  align-items: baseline;
  color: rgba(177, 198, 213, 0.6);
  font-size: 0.72rem;
}

.score-item strong {
  color: #dfe9ee;
}

.score-track {
  border: 0;
  background: rgba(126, 158, 181, 0.11);
}

.score-ai { background: linear-gradient(90deg, #ff7480, #ff9f90); }
.score-real { background: linear-gradient(90deg, #41c8bc, #7be0cc); }
.score-source { background: linear-gradient(90deg, #4f86aa, #6aa8c7); }

.image-block {
  height: 300px;
  border-color: rgba(120, 158, 185, 0.12);
  background:
    linear-gradient(rgba(132, 169, 194, 0.018) 1px, transparent 1px),
    linear-gradient(90deg, rgba(132, 169, 194, 0.018) 1px, transparent 1px),
    rgba(3, 14, 25, 0.58);
  background-size: 24px 24px;
}

.key-frame-grid figure,
.video-preview-missing {
  border-color: rgba(120, 158, 185, 0.12);
  background: rgba(3, 14, 25, 0.58);
}

.media-meta dl div {
  border-color: rgba(120, 158, 185, 0.09);
  background: rgba(40, 76, 103, 0.1);
}

.media-meta dt,
.metadata-list dt {
  color: rgba(164, 186, 203, 0.48);
}

.media-meta dd {
  color: rgba(205, 217, 225, 0.72);
}

.technical-details {
  margin: 0 28px 24px;
  padding: 0 18px;
}

.technical-details summary {
  min-height: 62px;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  align-content: center;
  column-gap: 12px;
}

.technical-details summary strong {
  color: #d8e3e9;
}

.technical-details summary span {
  color: rgba(165, 187, 203, 0.48);
}

.technical-content {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 28px;
}

.technical-content section {
  border-top-color: rgba(120, 158, 185, 0.1);
}

.technical-content section:first-child,
.technical-content .full-evidence-list {
  grid-column: 1 / -1;
}

.model-list li,
.metadata-list div {
  border-bottom-color: rgba(120, 158, 185, 0.08);
}

.metadata-list dd,
.model-list li {
  color: rgba(194, 209, 220, 0.67);
}

footer {
  border-top-color: rgba(120, 158, 185, 0.1);
  color: rgba(157, 179, 195, 0.46);
  background: rgba(3, 14, 25, 0.24);
}

@media (max-width: $tablet) {
  .result-overview,
  .report-layout {
    grid-template-columns: 1fr;
  }

  .media-pane {
    border-top: 1px solid rgba(120, 158, 185, 0.12);
    border-bottom: 0;
    border-left: 0;
  }
}

@media (max-width: $mobile) {
  .result-overview {
    padding: 22px 18px;
  }

  .result-facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .evidence-pane,
  .media-pane {
    padding: 18px;
  }

  .score-list,
  .technical-content {
    grid-template-columns: 1fr;
  }

  .evidence-list > li {
    grid-template-columns: 54px minmax(0, 1fr);
  }

  .technical-details {
    margin: 0 18px 18px;
  }

  .technical-content section:first-child,
  .technical-content .full-evidence-list {
    grid-column: auto;
  }
}

/* Desktop one-screen result summary. */
@media (min-width: 1025px) and (min-height: 720px) {
  .report {
    min-height: 0;
    height: 100%;
    display: grid;
    grid-template-rows: auto minmax(0, 1fr) auto auto;
  }

  .result-overview {
    grid-template-columns: minmax(0, 1fr) 260px;
    gap: 24px;
    padding: 18px 22px;
  }

  .status-line {
    gap: 7px;
  }

  .risk-badge,
  .engine-label {
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

  .recommendation {
    grid-template-columns: 64px minmax(0, 1fr);
    gap: 8px;
    margin-top: 9px;
    padding: 8px 10px;
  }

  .recommendation span,
  .recommendation p {
    font-size: 0.71rem;
    line-height: 1.45;
  }

  .result-facts {
    gap: 6px;
    padding: 6px;
  }

  .result-facts div,
  .result-facts .primary-fact {
    padding: 8px 10px;
  }

  .result-facts .primary-fact dd {
    font-size: 1.45rem;
  }

  .result-facts dt {
    font-size: 0.65rem;
  }

  .result-facts dd {
    font-size: 0.73rem;
  }

  .report-layout {
    min-height: 0;
    overflow: hidden;
  }

  .evidence-pane,
  .media-pane {
    min-height: 0;
    padding: 14px;
    overflow: hidden;
  }

  .evidence-pane {
    gap: 8px;
  }

  .content-section,
  .key-evidence,
  .evidence-strength {
    min-height: 0;
    padding: 12px 14px;
  }

  .section-title h3 {
    font-size: 0.92rem;
  }

  .section-title > span,
  .section-title div > span {
    font-size: 0.63rem;
  }

  .row-title small {
    font-size: 0.66rem;
  }

  .evidence-list {
    gap: 6px;
    margin-top: 9px;
  }

  .evidence-list > li {
    grid-template-columns: 56px minmax(0, 1fr) auto;
    gap: 10px;
    padding: 9px 10px;
  }

  .evidence-list strong {
    font-size: 0.77rem;
  }

  .evidence-list p {
    display: -webkit-box;
    margin-top: 2px;
    overflow: hidden;
    font-size: 0.69rem;
    line-height: 1.45;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
  }

  .evidence-category,
  .evidence-score {
    font-size: 0.66rem;
  }

  .score-list {
    gap: 12px;
    margin-top: 9px;
  }

  .score-item > div:first-child {
    font-size: 0.66rem;
  }

  .score-track {
    height: 5px;
    margin-top: 5px;
  }

  .media-pane {
    display: flex;
    flex-direction: column;
  }

  .image-block {
    min-height: 0;
    height: auto;
    flex: 1 1 auto;
    margin-top: 8px;
  }

  .video-visualization {
    min-height: 0;
    flex: 1 1 auto;
    gap: 8px;
    margin-top: 8px;
    overflow: hidden;
  }

  .key-frame-grid figure {
    height: 88px;
  }

  .timeline-card {
    padding: 10px;
  }

  .timeline-list {
    gap: 4px;
    margin-top: 8px;
  }

  .media-meta {
    flex: 0 0 auto;
    margin-top: 8px;
  }

  .media-meta > strong {
    font-size: 0.77rem;
  }

  .media-meta dl {
    gap: 6px;
    margin-top: 7px;
  }

  .media-meta dl div {
    padding: 6px 7px;
  }

  .media-meta dt,
  .media-meta dd {
    font-size: 0.64rem;
  }

  .technical-details {
    margin: 0 14px 8px;
    padding: 0 14px;
  }

  .technical-details summary {
    min-height: 42px;
  }

  .technical-details summary strong {
    font-size: 0.75rem;
  }

  .technical-details summary span {
    font-size: 0.66rem;
  }

  footer {
    min-height: 30px;
    padding: 0 18px;
    font-size: 0.62rem;
  }
}

/* Essential report: conclusion, signal, action and two findings only. */
.report.essential-report {
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

.essential-body {
  min-width: 0;
  min-height: 0;
  flex: 1 1 auto;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  align-items: stretch;
}

.essential-text {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
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
  -webkit-line-clamp: 2;
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

.essential-media {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 25px 24px 26px;
  border-left: 1px solid rgba(120, 158, 185, 0.1);
  background:
    linear-gradient(180deg, rgba(18, 43, 62, 0.32), rgba(4, 15, 27, 0.18));
}

.essential-media-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.essential-media-heading > div {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.essential-media-heading span {
  color: #74a9c6;
  font-size: 0.74rem;
  font-weight: 850;
  letter-spacing: 0.08em;
}

.essential-media-heading strong {
  color: #e7eef2;
  font-size: 1.02rem;
  line-height: 1.35;
}

.essential-media-heading small {
  padding: 4px 7px;
  color: rgba(144, 181, 202, 0.7);
  border: 1px solid rgba(111, 165, 194, 0.16);
  border-radius: 6px;
  background: rgba(24, 63, 88, 0.26);
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: 0.1em;
}

.essential-media-frame {
  min-height: 240px;
  flex: 1 1 auto;
  display: grid;
  place-items: center;
  margin: 0;
  overflow: hidden;
  border: 1px solid rgba(120, 169, 197, 0.14);
  border-radius: 13px;
  background:
    linear-gradient(135deg, rgba(19, 46, 64, 0.34), rgba(2, 9, 17, 0.9));
  box-shadow: inset 0 0 28px rgba(0, 0, 0, 0.22);
}

.essential-media-frame img,
.essential-media-frame video {
  width: 100%;
  height: 100%;
  max-height: 380px;
  display: block;
  object-fit: contain;
  background: rgba(2, 8, 15, 0.72);
}

.essential-media-frame.is-video {
  min-height: 0;
  flex: 0 0 auto;
  aspect-ratio: 16 / 9;
}

.essential-video-timeline {
  display: grid;
  gap: 7px;
}

.essential-video-timeline-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.essential-video-timeline-heading span {
  color: rgba(235, 184, 187, 0.74);
  font-size: 0.69rem;
  font-weight: 780;
}

.essential-video-timeline-heading small {
  color: rgba(154, 176, 191, 0.48);
  font-size: 0.62rem;
}

.essential-video-track {
  height: 7px;
  position: relative;
  border: 1px solid rgba(255, 103, 114, 0.18);
  border-radius: 999px;
  background: rgba(255, 91, 104, 0.1);
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.34);
}

.essential-risk-range {
  min-width: 4px;
  position: absolute;
  top: -1px;
  bottom: -1px;
  border-radius: 999px;
  background: linear-gradient(90deg, #dc4f5f, #ff7580);
  box-shadow: 0 0 9px rgba(255, 82, 96, 0.34);
}

.essential-frame-marker {
  width: 2px;
  height: 13px;
  position: absolute;
  top: 50%;
  z-index: 1;
  border-radius: 2px;
  background: #ff9aa2;
  box-shadow: 0 0 6px rgba(255, 99, 112, 0.52);
  transform: translate(-1px, -50%);
}

.essential-frame-strip {
  display: grid;
  gap: 7px;
}

.essential-frame-strip-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.essential-frame-strip-heading span {
  color: rgba(174, 197, 211, 0.66);
  font-size: 0.69rem;
  font-weight: 760;
}

.essential-frame-strip-heading small {
  color: rgba(143, 172, 190, 0.48);
  font-size: 0.66rem;
}

.essential-frame-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

.essential-frame-grid figure {
  min-width: 0;
  aspect-ratio: 4 / 3;
  position: relative;
  margin: 0;
  overflow: hidden;
  border: 1px solid rgba(120, 169, 197, 0.13);
  border-radius: 8px;
  background: rgba(2, 8, 15, 0.72);
}

.essential-frame-grid img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}

.essential-frame-grid figcaption {
  position: absolute;
  right: 4px;
  bottom: 4px;
  padding: 2px 4px;
  color: rgba(239, 246, 249, 0.9);
  border-radius: 4px;
  background: rgba(2, 8, 15, 0.74);
  font-size: 0.58rem;
  font-weight: 760;
}

.essential-media-empty {
  max-width: 150px;
  color: rgba(163, 184, 198, 0.5);
  font-size: 0.78rem;
  line-height: 1.6;
  text-align: center;
}

.essential-media-name {
  margin: 0;
  overflow: hidden;
  color: rgba(185, 202, 213, 0.6);
  font-size: 0.74rem;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
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

  .essential-media {
    gap: 10px;
    padding: 16px 18px 18px;
  }

  .essential-media-frame {
    min-height: 210px;
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

  .essential-media {
    gap: 7px;
    padding: 11px 14px 12px;
  }

  .essential-media-frame {
    min-height: 165px;
  }

  .essential-media-frame.is-video {
    height: 116px;
    min-height: 116px;
    aspect-ratio: auto;
  }

  .essential-video-timeline {
    gap: 4px;
  }

  .essential-frame-strip {
    gap: 4px;
  }

  .essential-frame-grid figure {
    height: 46px;
    aspect-ratio: auto;
  }

  .essential-report .essential-footer {
    padding: 7px 24px;
  }
}

@media (max-width: 900px) {
  .essential-body {
    grid-template-columns: 1fr;
  }

  .essential-media {
    border-top: 1px solid rgba(120, 158, 185, 0.1);
    border-left: 0;
  }

  .essential-media-frame {
    min-height: 220px;
    max-height: 360px;
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

  .essential-media {
    padding: 20px;
  }

  .essential-media-frame {
    min-height: 200px;
    max-height: 300px;
  }
}
</style>
