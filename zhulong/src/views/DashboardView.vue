<template>
  <div
    ref="dashboardRef"
    class="dashboard"
    :class="{
      'is-home': !selectedFile && selectedMediaType !== 'article' && !taskReport,
      'is-workspace': Boolean(selectedFile) || selectedMediaType === 'article' || Boolean(taskReport),
      'is-report': Boolean(taskReport)
    }"
    @dragover.prevent="handleDragOver"
    @dragleave="handleDragLeave"
    @drop.prevent="handleDrop"
  >
    <input
      ref="fileInputRef"
      class="file-input"
      type="file"
      :accept="pickerAccept"
      @change="handleFileSelect"
    />

    <header class="app-header">
      <button class="brand" type="button" @click="resetWorkbench" aria-label="返回烛龙鉴伪主界面">
        <span class="brand-copy">
          <strong>烛龙</strong>
          <small>AI 内容鉴伪</small>
        </span>
      </button>

      <div class="header-actions">
        <span v-if="isDemoMode" class="demo-mode-badge">静态演示 · 文件不上传</span>
        <button class="header-button" type="button" @click="showHistory = true">
          <Clock3 :size="16" aria-hidden="true" />
          <span>历史记录</span>
        </button>
        <span class="user-name">{{ user?.username || '访客' }}</span>
        <button class="logout-button" type="button" aria-label="退出登录" @click="handleLogout">
          <LogOut :size="17" aria-hidden="true" />
          <span>退出</span>
        </button>
      </div>
    </header>

    <main v-if="!selectedFile && selectedMediaType !== 'article' && !taskReport" class="home-main">
      <div class="home-vignette" aria-hidden="true"></div>
      <div class="ambient-light ambient-violet" aria-hidden="true"></div>
      <div class="ambient-light ambient-indigo" aria-hidden="true"></div>
      <div class="ambient-light ambient-fuchsia" aria-hidden="true"></div>
      <div class="ambient-light ambient-ember" aria-hidden="true"></div>

      <section class="hero" aria-labelledby="home-title">
        <div class="hero-title">
          <h1 id="home-title">今天想鉴别什么？</h1>
          <span aria-hidden="true"></span>
        </div>
        <p>粘贴文字或上传图片、视频，系统会自动选择对应模型并开始检测</p>

        <div class="composer-wrap" :class="{ dragging: isDragging }">
          <MediaChatComposer
            v-model="chatMessage"
            @attach="openPicker('all', { autoStart: true })"
            @submit="handleChatSubmit"
          />
          <p v-if="chatNotice || taskError" class="home-notice" role="status">
            {{ taskError || chatNotice }}
          </p>
        </div>

        <div class="quick-actions" aria-label="快捷操作">
          <button type="button" @click="openPicker('image')">
            <ImageIcon :size="16" />
            <span>图片风险筛查</span>
          </button>
          <button type="button" @click="openPicker('video')">
            <FileVideo2 :size="16" />
            <span>视频联合鉴伪</span>
          </button>
          <button type="button" @click="openArticleWorkspace">
            <FileText :size="16" />
            <span>AI 文字检测</span>
          </button>
        </div>

        <p class="service-readiness" :class="serviceReadinessClass" role="status">
          <span aria-hidden="true"></span>
          {{ serviceReadinessLabel }}
        </p>
      </section>
    </main>

    <main v-else class="app-main">
      <section class="page-heading" aria-labelledby="page-title">
        <div>
          <button class="back-home" type="button" @click="resetWorkbench">
            <ArrowLeft :size="15" /> 返回主界面
          </button>
          <p class="eyebrow">{{ workspaceEyebrow }}</p>
          <h1 id="page-title">{{ workspaceTitle }}</h1>
          <p>{{ workspaceSubtitle }}</p>
        </div>

        <ol class="flow-steps" aria-label="检测流程">
          <li
            v-for="(step, index) in flowSteps"
            :key="step"
            :class="{ active: currentFlowStep === index + 1, completed: currentFlowStep > index + 1 }"
          >
            <span>{{ index + 1 }}</span>
            {{ step }}
          </li>
        </ol>
      </section>

      <section v-if="taskReport" class="result-workspace" aria-label="检测结果">
        <div class="result-toolbar">
          <div>
            <span>{{ taskReport?.mediaType === 'article' ? '文字风险报告已生成' : '检测完成' }}</span>
            <strong>{{ selectedFile?.name || articleTitle || '未命名文章' }}</strong>
          </div>
          <button class="secondary-button" type="button" @click="resetWorkbench">
            <RotateCcw :size="16" /> 检测新素材
          </button>
        </div>
        <ArticleResultReport
          v-if="taskReport?.mediaType === 'article'"
          :report="taskReport"
          @restart="resetWorkbench"
        />
        <UnifiedResultReport
          v-else
          :report="taskReport"
          :preview-url="previewUrl"
          @restart="resetWorkbench"
        />
      </section>

      <section v-else class="analysis-workspace" aria-label="媒体检测工作台">
        <div v-if="selectedMediaType === 'article'" class="article-editor-column">
          <div class="section-heading">
            <div>
              <span>核查对象</span>
              <h2>待检测文字与辅助来源</h2>
            </div>
            <small>{{ articleText.length.toLocaleString() }} / 100,000 字符</small>
          </div>

          <div class="article-editor-card">
            <label class="article-field article-title-field">
              <span>标题（可选）</span>
              <input
                v-model.trim="articleTitle"
                type="text"
                maxlength="500"
                placeholder="输入文章标题"
              />
            </label>

            <label class="article-field article-body-field">
              <span>正文</span>
              <textarea
                v-model="articleText"
                maxlength="100000"
                placeholder="粘贴至少约 100 个中文字。系统会分段分析 AI 写作风格信号，并保留声明与来源核查线索。"
              ></textarea>
            </label>

            <div class="article-origin-grid">
              <label class="article-field">
                <span>声明的原文网址（可选）</span>
                <input
                  v-model.trim="articleDeclaredUrl"
                  type="url"
                  placeholder="https://example.com/article"
                />
              </label>
              <label class="article-field">
                <span>声明的作者（可选）</span>
                <input
                  v-model.trim="articleDeclaredAuthor"
                  type="text"
                  maxlength="500"
                  placeholder="作者或发布机构"
                />
              </label>
              <label class="article-field">
                <span>声明的发布时间（可选）</span>
                <input
                  v-model.trim="articleDeclaredPublishedAt"
                  type="text"
                  maxlength="100"
                  placeholder="例如 2026-07-18 10:00"
                />
              </label>
            </div>

            <p class="article-offline-note">
              <LockKeyhole :size="14" />
              本轮使用本地实验性模型，不访问任何网址；模型信号不能证明真实作者身份。
            </p>
          </div>
        </div>

        <div v-else class="media-column">
          <div class="section-heading">
            <div>
              <span>检测对象</span>
              <h2>{{ mediaTypeLabel }}预览</h2>
            </div>
            <button v-if="!taskLoading" class="text-button" type="button" @click="openPicker(selectedMediaType)">
              重新选择
            </button>
          </div>

          <div
            class="dropzone ready"
            :class="[{ dragging: isDragging }, `preview-${previewOrientation}`]"
            @dragover.prevent="handleDragOver"
            @dragleave="handleDragLeave"
            @drop.prevent="handleDrop"
          >
            <figure class="media-preview">
              <video
                v-if="selectedMediaType === 'video'"
                :src="previewUrl"
                :aria-label="selectedFile.name"
                controls
                preload="metadata"
              ></video>
              <img v-else :src="previewUrl" :alt="selectedFile.name" />
              <button
                v-if="!taskLoading && selectedMediaType === 'image'"
                class="preview-expand"
                type="button"
                aria-label="全屏查看完整图片"
                @click="showImagePreview = true"
              >
                <Maximize2 :size="15" />
                查看完整图片
              </button>
              <div v-if="taskLoading" class="analyzing-overlay" aria-hidden="true">
                <span></span>
                <small>正在分析{{ mediaTypeLabel }}证据</small>
              </div>
            </figure>
          </div>

          <div class="file-summary">
            <div class="file-identity">
              <span class="file-type-icon" :class="selectedMediaType">
                <FileVideo2 v-if="selectedMediaType === 'video'" :size="19" />
                <FileImage v-else :size="19" />
              </span>
              <div>
                <strong :title="selectedFile.name">{{ selectedFile.name }}</strong>
                <span>{{ formatFileSize(selectedFile.size) }} · {{ selectedFile.type || `${mediaTypeLabel}文件` }}</span>
              </div>
            </div>
            <dl>
              <div>
                <dt>分辨率</dt>
                <dd>{{ mediaDimensionsLabel }}</dd>
              </div>
              <div>
                <dt>{{ selectedMediaType === 'video' ? '时长' : '来源' }}</dt>
                <dd>{{ selectedMediaType === 'video' ? mediaDurationLabel : selectedSourceLabel }}</dd>
              </div>
            </dl>
          </div>
        </div>

        <aside class="control-column" aria-label="检测设置与状态">
          <UnifiedTaskStatus
            v-if="taskLoading"
            :task-id="currentTask?.id"
            :status="taskStatus"
            :media-type="selectedMediaType"
          />

          <template v-else>
            <div class="control-heading">
              <span>检测设置</span>
              <h2>{{ controlHeading }}</h2>
              <p>{{ controlDescription }}</p>
            </div>

            <div v-if="selectedMediaType !== 'article' && chatMessage.trim()" class="task-intention">
              <MessageSquareText :size="16" aria-hidden="true" />
              <div><span>本次备注（不改变检测模型）</span><p>{{ chatMessage.trim() }}</p></div>
            </div>

            <fieldset v-if="selectedMediaType === 'image'" class="source-options">
              <legend class="sr-only">素材来源</legend>
              <label v-for="option in sourceOptions" :key="option.value" :class="{ selected: sourceHint === option.value }">
                <input v-model="sourceHint" type="radio" name="source-hint" :value="option.value" />
                <span>{{ option.label }}</span>
              </label>
            </fieldset>

            <p v-if="selectedMediaType === 'image'" class="source-description">{{ sourceDescription }}</p>

            <div v-if="taskError" class="error-message" role="alert">{{ taskError }}</div>

            <div class="capability-list">
              <span>本次将分析</span>
              <ul>
                <li v-for="item in activeCapabilities" :key="item"><Check :size="14" /> {{ item }}</li>
              </ul>
            </div>

            <div class="control-footer">
              <small>{{ controlDuration }}</small>
              <button class="primary-button" type="button" @click="startUnifiedDetection">
                <ScanSearch :size="17" /> {{ primaryActionLabel }}
              </button>
            </div>
          </template>
        </aside>
      </section>
    </main>

    <aside v-if="showHistory" class="history-overlay" role="dialog" aria-modal="true" aria-label="历史记录" @click.self="showHistory = false">
      <div class="history-panel">
        <div class="history-header">
          <div>
            <span>RECENT TASKS</span>
            <h2>历史记录</h2>
          </div>
          <button class="close-button" type="button" aria-label="关闭历史记录" @click="showHistory = false">
            <X :size="19" />
          </button>
        </div>
        <HistoryList />
      </div>
    </aside>

    <Teleport to="body">
      <Transition name="preview-fade">
        <div
          v-if="showImagePreview && previewUrl"
          class="image-lightbox"
          role="dialog"
          aria-modal="true"
          aria-label="完整图片预览"
          @click.self="showImagePreview = false"
        >
          <button class="lightbox-close" type="button" aria-label="关闭完整图片预览" @click="showImagePreview = false">
            <X :size="20" />
          </button>
          <figure>
            <img :src="previewUrl" :alt="selectedFile?.name || '完整图片预览'" />
            <figcaption>
              <strong>{{ selectedFile?.name }}</strong>
              <span>{{ mediaDimensionsLabel }} · 图片已按原始比例完整显示</span>
            </figcaption>
          </figure>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowLeft,
  Check,
  Clock3,
  FileImage,
  FileText,
  FileVideo2,
  Image as ImageIcon,
  LockKeyhole,
  LogOut,
  Maximize2,
  MessageSquareText,
  RotateCcw,
  ScanSearch,
  X
} from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { useHistoryStore } from '@/stores/history'
import { navigateWithoutTransition } from '@/composables/useRouteTransition'
import MediaChatComposer from '@/components/ui/MediaChatComposer.vue'
import ArticleResultReport from '@/components/ArticleResultReport.vue'
import UnifiedResultReport from '@/components/UnifiedResultReport.vue'
import UnifiedTaskStatus from '@/components/UnifiedTaskStatus.vue'
import { detectInputType, runDetectionTask } from '@/services/detectionAgent'
import { runArticleVerification } from '@/services/articleVerificationAgent'
import { isDemoMode } from '@/services/demoMode'

const HistoryList = defineAsyncComponent(() => import('@/components/HistoryList.vue'))

const router = useRouter()
const authStore = useAuthStore()
const historyStore = useHistoryStore()

const IMAGE_ACCEPT = '.jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp'
const VIDEO_ACCEPT = '.mp4,.mov,.avi,.webm,video/mp4,video/quicktime,video/x-msvideo,video/webm'
const MEDIA_ACCEPT = `${IMAGE_ACCEPT},${VIDEO_ACCEPT}`
const supportedImageExtensions = new Set(['jpg', 'jpeg', 'png', 'webp'])
const supportedVideoExtensions = new Set(['mp4', 'mov', 'avi', 'webm'])
const sourceOptions = [
  { value: 'auto', label: '自动判断' },
  { value: 'camera_export', label: '相机/手机拍摄' },
  { value: 'screen_capture', label: '截图或录屏' },
  { value: 'game_capture', label: '游戏/虚拟画面' },
  { value: 'unknown', label: '来源不明' }
]

const selectedFile = ref(null)
const selectedMediaType = ref('')
const dashboardRef = ref(null)
const fileInputRef = ref(null)
const pickerAccept = ref(IMAGE_ACCEPT)
const previewUrl = ref('')
const mediaMetadata = ref(null)
const isDragging = ref(false)
const showHistory = ref(false)
const showImagePreview = ref(false)
const taskLoading = ref(false)
const currentTask = ref(null)
const taskStatus = ref(null)
const taskReport = ref(null)
const taskError = ref('')
const sourceHint = ref('auto')
const chatMessage = ref('')
const chatNotice = ref('')
const articleTitle = ref('')
const articleText = ref('')
const articleDeclaredUrl = ref('')
const articleDeclaredAuthor = ref('')
const articleDeclaredPublishedAt = ref('')
const pickerAutoStart = ref(false)
const serviceReadiness = ref(isDemoMode
  ? { checking: false, imageReady: true, textReady: true, videoReady: true }
  : { checking: true, imageReady: false, textReady: false, videoReady: false })
let readinessTimer = null
let dashboardDisposed = false

const user = computed(() => authStore.user)
const serviceReadinessClass = computed(() => {
  if (serviceReadiness.value.checking) return 'is-checking'
  if (serviceReadiness.value.imageReady && serviceReadiness.value.textReady && serviceReadiness.value.videoReady) return 'is-ready'
  if (serviceReadiness.value.imageReady || serviceReadiness.value.textReady || serviceReadiness.value.videoReady) return 'is-partial'
  return 'is-unavailable'
})
const serviceReadinessLabel = computed(() => {
  if (isDemoMode) return '当前为固定演示数据；素材只在浏览器中预览'
  if (serviceReadiness.value.checking) return '正在确认本地模型状态…'
  if (serviceReadiness.value.imageReady && serviceReadiness.value.textReady && serviceReadiness.value.videoReady) return '图片、视频与文字模型均已就绪'
  const readyLabels = [
    serviceReadiness.value.imageReady ? '图片' : '',
    serviceReadiness.value.videoReady ? '视频' : '',
    serviceReadiness.value.textReady ? '文字' : ''
  ].filter(Boolean)
  if (readyLabels.length) return `${readyLabels.join('、')}模型已就绪，其余模型仍在加载`
  return '本地模型服务尚未就绪，请稍后再试'
})
const mediaTypeLabel = computed(() => ({
  image: '图片',
  video: '视频',
  article: '文章'
}[selectedMediaType.value] || '内容'))
const workspaceEyebrow = computed(() => ({
  image: 'IMAGE AI FORENSICS',
  video: 'AI VIDEO FORENSICS',
  article: 'CHINESE AI WRITING SIGNAL'
}[selectedMediaType.value] || 'CONTENT VERIFICATION'))
const workspaceTitle = computed(() => ({
  image: '图片 AI 生成实验性风险评估',
  video: 'AI 生视频与换脸联合鉴别',
  article: '中文 AI 写作风格检测'
}[selectedMediaType.value] || '内容核查'))
const workspaceSubtitle = computed(() => ({
  image: '使用 DDA 与 Community Forensics 双模型交叉检测，并结合生成元数据和来源线索；证据冲突时保留无法确认。',
  video: '联合分析完整 AI 生成、换脸与时序异常；阴性结果只表示模型弃权，不证明视频真实。',
  article: '使用本地中文 BERT 分段分析写作风格信号；结果不证明作者身份，并保留离线声明与来源线索。'
}[selectedMediaType.value] || ''))
const flowSteps = computed(() => selectedMediaType.value === 'article'
  ? ['粘贴文字', '确认范围', '分段分析', '查看报告']
  : [`选择${mediaTypeLabel.value}`, '确认来源', '分析证据', '查看结论'])
const currentFlowStep = computed(() => {
  if (taskReport.value) return 4
  if (taskLoading.value) return 3
  if (selectedFile.value || selectedMediaType.value === 'article') return 2
  return 1
})
const mediaDimensionsLabel = computed(() => mediaMetadata.value?.width && mediaMetadata.value?.height
  ? `${mediaMetadata.value.width} × ${mediaMetadata.value.height}`
  : '读取中')
const mediaDurationLabel = computed(() => {
  const duration = Number(mediaMetadata.value?.duration)
  if (!Number.isFinite(duration)) return '读取中'
  const minutes = Math.floor(duration / 60)
  const seconds = Math.floor(duration % 60)
  return `${minutes}:${String(seconds).padStart(2, '0')}`
})
const previewOrientation = computed(() => {
  const width = Number(mediaMetadata.value?.width)
  const height = Number(mediaMetadata.value?.height)
  if (!width || !height) return 'standard'
  const ratio = width / height
  if (ratio < 0.78) return 'portrait'
  if (ratio > 1.7) return 'wide'
  return 'standard'
})
const selectedSourceLabel = computed(() => sourceOptions.find((option) => option.value === sourceHint.value)?.label || '自动判断')
const activeCapabilities = computed(() => ({
  image: ['双模型 AI 生成信号', '来源与 EXIF 线索', '内容与元数据证据'],
  video: ['完整 AI 生视频信号', '人脸换脸与操纵信号', 'D3 时序辅助证据', '采样帧风险时间轴'],
  article: ['中文 BERT 分段信号', '重点段落排序', '正文 SHA-256 指纹', '声明与来源辅助线索']
}[selectedMediaType.value] || []))
const controlHeading = computed(() => ({
  image: '确认素材来源',
  video: '确认联合检测范围',
  article: '确认文字检测范围'
}[selectedMediaType.value] || '确认范围'))
const controlDescription = computed(() => ({
  image: 'DDA 与 Community Forensics 均达到强阈值才形成高风险结论；当前仅完成本地小样本校准。',
  video: '完整生成需 AEGIS 与 D3 同时满足保守门槛，换脸由 LNCLIP 独立检测；结果不可用于司法鉴定。',
  article: '当前模型仅输出实验性写作风格信号；短文本、人工改写和陌生文体可能误判或漏判。'
}[selectedMediaType.value] || ''))
const controlDuration = computed(() => ({
  article: '首次加载模型较慢，之后通常只需数秒',
  image: '模型就绪后，单张图片分析通常只需数秒',
  video: '视频联合分析通常需要 30–120 秒'
}[selectedMediaType.value] || ''))
const primaryActionLabel = computed(() => ({
  article: '开始文字检测',
  image: '开始风险筛查',
  video: '开始联合鉴伪'
}[selectedMediaType.value] || '开始分析'))
const sourceDescription = computed(() => ({
  auto: '系统将根据格式、分辨率和元数据自动判断来源场景。',
  camera_export: '这是未经验证的用户声明；相机来源仍需文件内可观测元数据支持。',
  screen_capture: '这是未经验证的用户声明；截图场景只会触发更保守的解释。',
  game_capture: '这是未经验证的用户声明；游戏与虚拟画面只会触发更保守的解释。',
  unknown: '来源不明时，系统会降低对单一模型结论的依赖。'
}[sourceHint.value]))

const refreshServiceReadiness = async (scheduleRetry = true) => {
  if (isDemoMode) {
    serviceReadiness.value = {
      checking: false,
      imageReady: true,
      textReady: true,
      videoReady: true
    }
    return serviceReadiness.value
  }

  if (readinessTimer) {
    clearTimeout(readinessTimer)
    readinessTimer = null
  }

  let health = null
  for (const baseUrl of ['http://localhost:5002', 'http://127.0.0.1:5002']) {
    const controller = new AbortController()
    // The aggregate endpoint checks all three local model services. On a cold
    // start this can legitimately take several seconds, so do not abort before
    // the backend has had time to finish its own health probes.
    const timerId = setTimeout(() => controller.abort(), 12000)
    try {
      const response = await fetch(`${baseUrl}/api/health`, {
        cache: 'no-store',
        signal: controller.signal
      })
      if (response.ok) {
        health = await response.json()
        break
      }
    } catch {
      // Try the alternate loopback hostname before reporting unavailable.
    } finally {
      clearTimeout(timerId)
    }
  }

  serviceReadiness.value = {
    checking: false,
    imageReady: health?.image_detector?.ready === true,
    textReady: health?.text_detector?.ready === true,
    videoReady: health?.video_detector?.ready === true
  }

  if (
    scheduleRetry
    && !dashboardDisposed
    && (
      !serviceReadiness.value.imageReady
      || !serviceReadiness.value.textReady
      || !serviceReadiness.value.videoReady
    )
  ) {
    readinessTimer = setTimeout(() => refreshServiceReadiness(true), 3000)
  }

  return serviceReadiness.value
}

const openPicker = async (kind = 'all', options = {}) => {
  pickerAutoStart.value = options.autoStart === true
  pickerAccept.value = kind === 'image'
    ? IMAGE_ACCEPT
    : kind === 'video'
      ? VIDEO_ACCEPT
      : MEDIA_ACCEPT
  taskError.value = ''
  chatNotice.value = ''
  await nextTick()
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
    fileInputRef.value.click()
  }
}

const openArticleWorkspace = async () => {
  releasePreview()
  selectedFile.value = null
  selectedMediaType.value = 'article'
  mediaMetadata.value = null
  sourceHint.value = 'auto'
  taskError.value = ''
  chatNotice.value = ''
  resetTask()
  await nextTick()
  dashboardRef.value?.scrollTo({ top: 0, behavior: 'smooth' })
}

const handleChatSubmit = async () => {
  const pastedText = chatMessage.value.trim()
  if (!pastedText || taskLoading.value) return

  try {
    const detected = detectInputType({ text: pastedText })
    if (detected.type !== 'article') return
    if (pastedText.length > 100000) {
      throw new Error('文字超过 100,000 个字符，请删减后再检测')
    }

    await openArticleWorkspace()
    articleTitle.value = '主界面粘贴文字'
    articleText.value = pastedText
    chatMessage.value = ''
    await nextTick()
    await startUnifiedDetection()
  } catch (error) {
    taskError.value = error.message || '无法识别输入内容'
  }
}

const handleFileSelect = async (event) => {
  const file = event.target.files?.[0]
  const shouldAutoStart = pickerAutoStart.value
  pickerAutoStart.value = false
  if (!file) return
  const accepted = await setFile(file)
  if (accepted && shouldAutoStart) await startUnifiedDetection()
}

const handleDragOver = () => {
  if (!taskLoading.value) isDragging.value = true
}

const handleDragLeave = (event) => {
  if (!event.currentTarget.contains(event.relatedTarget)) isDragging.value = false
}

const handleDrop = async (event) => {
  isDragging.value = false
  if (taskLoading.value) return
  const file = event.dataTransfer.files?.[0]
  if (!file) return
  const shouldAutoStart = (
    !selectedFile.value
    && selectedMediaType.value !== 'article'
    && !taskReport.value
  )
  const accepted = await setFile(file)
  if (accepted && shouldAutoStart) await startUnifiedDetection()
}

const readImageMetadata = (url) => new Promise((resolve, reject) => {
  const image = new Image()
  image.onload = () => resolve({ width: image.naturalWidth, height: image.naturalHeight, duration: null })
  image.onerror = () => reject(new Error('无法读取图片内容，请确认文件未损坏'))
  image.src = url
})

const readVideoMetadata = (url) => new Promise((resolve, reject) => {
  const video = document.createElement('video')
  video.preload = 'metadata'
  video.onloadedmetadata = () => resolve({
    width: video.videoWidth,
    height: video.videoHeight,
    duration: Number.isFinite(video.duration) ? video.duration : null
  })
  video.onerror = () => reject(new Error('无法读取视频内容，请确认文件未损坏或编码受浏览器支持'))
  video.src = url
})

const releasePreview = () => {
  showImagePreview.value = false
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}

const setFile = async (file) => {
  taskError.value = ''
  chatNotice.value = ''
  let nextPreview = ''

  try {
    const extension = file.name.split('.').pop()?.toLowerCase() || ''
    const detected = detectInputType({ file })
    if (detected.type === 'image' && !supportedImageExtensions.has(extension)) {
      throw new Error('图片支持 JPG、PNG 和 WebP 格式')
    }
    if (detected.type === 'video' && !supportedVideoExtensions.has(extension)) {
      throw new Error('视频支持 MP4、MOV、AVI 和 WebM 格式')
    }

    const sizeLimit = detected.type === 'video' ? 100 * 1024 * 1024 : 20 * 1024 * 1024
    if (file.size > sizeLimit) {
      throw new Error(detected.type === 'video'
        ? '视频超过 100MB，请压缩或截取后重试'
        : '图片超过 20MB，请压缩后重试')
    }

    nextPreview = URL.createObjectURL(file)
    const metadata = detected.type === 'video'
      ? await readVideoMetadata(nextPreview)
      : await readImageMetadata(nextPreview)

    if (detected.type === 'image' && metadata.width * metadata.height > 60_000_000) {
      throw new Error('图片超过 6000 万像素，请缩小分辨率后重试')
    }

    releasePreview()
    selectedFile.value = file
    selectedMediaType.value = detected.type
    previewUrl.value = nextPreview
    nextPreview = ''
    mediaMetadata.value = metadata
    articleTitle.value = ''
    articleText.value = ''
    articleDeclaredUrl.value = ''
    articleDeclaredAuthor.value = ''
    articleDeclaredPublishedAt.value = ''
    sourceHint.value = 'auto'
    resetTask()
    await nextTick()
    dashboardRef.value?.scrollTo({ top: 0, behavior: 'smooth' })
    return true
  } catch (error) {
    if (nextPreview) URL.revokeObjectURL(nextPreview)
    taskError.value = error.message || '无法读取该媒体文件'
    if (fileInputRef.value) fileInputRef.value.value = ''
    return false
  }
}

const resetTask = () => {
  currentTask.value = null
  taskStatus.value = null
  taskReport.value = null
  taskError.value = ''
  taskLoading.value = false
}

const resetWorkbench = () => {
  showImagePreview.value = false
  releasePreview()
  selectedFile.value = null
  selectedMediaType.value = ''
  mediaMetadata.value = null
  sourceHint.value = 'auto'
  chatMessage.value = ''
  chatNotice.value = ''
  articleTitle.value = ''
  articleText.value = ''
  articleDeclaredUrl.value = ''
  articleDeclaredAuthor.value = ''
  articleDeclaredPublishedAt.value = ''
  pickerAutoStart.value = false
  if (fileInputRef.value) fileInputRef.value.value = ''
  resetTask()
  nextTick(() => dashboardRef.value?.scrollTo({ top: 0 }))
}

const startUnifiedDetection = async () => {
  if (taskLoading.value) return
  if (selectedMediaType.value === 'article') {
    if (!articleText.value.trim()) {
      taskError.value = '请先粘贴需要核查的文章正文'
      return
    }
  } else if (!selectedFile.value) {
    return
  }

  const requiredServiceReady = ({
    article: serviceReadiness.value.textReady,
    image: serviceReadiness.value.imageReady,
    video: serviceReadiness.value.videoReady
  })[selectedMediaType.value]
  if (!requiredServiceReady) {
    const latestReadiness = await refreshServiceReadiness(false)
    const nowReady = ({
      article: latestReadiness.textReady,
      image: latestReadiness.imageReady,
      video: latestReadiness.videoReady
    })[selectedMediaType.value]
    if (!nowReady) {
      taskError.value = ({
        article: '文字模型仍在加载或未成功启动，请稍后再试；可查看 logs/ai-image-text-detector.log',
        image: '图片模型仍在加载或未成功启动，请稍后再试；可查看 logs/ai-image-text-detector.log',
        video: '视频模型仍在加载或未成功启动，请稍后再试；可查看 logs/video-forensics.log'
      })[selectedMediaType.value] || '本地模型仍在加载，请稍后再试'
      refreshServiceReadiness(true)
      return
    }
  }

  taskLoading.value = true
  taskError.value = ''
  taskReport.value = null
  await nextTick()
  dashboardRef.value?.scrollTo({ top: 0, behavior: 'smooth' })

  try {
    const callbacks = {
      onTask: (task) => { currentTask.value = task },
      onStatus: (status) => { taskStatus.value = status }
    }
    const outcome = selectedMediaType.value === 'article'
      ? await runArticleVerification({
        title: articleTitle.value,
        text: articleText.value,
        declared_url: articleDeclaredUrl.value,
        declared_author: articleDeclaredAuthor.value,
        declared_published_at: articleDeclaredPublishedAt.value
      }, callbacks)
      : await runDetectionTask({
        file: selectedFile.value,
        sourceHint: sourceHint.value,
        previewUrl: previewUrl.value
      }, callbacks)

    taskReport.value = outcome.report
    await nextTick()
    dashboardRef.value?.scrollTo({ top: 0 })
    await historyStore.addRecord({
      task_id: outcome.report.taskId,
      type: outcome.report.mediaType,
      result: outcome.report.mediaType === 'article'
        ? outcome.report.verdict
        : outcome.report.riskLevel === 'low' ? 'likely_real' : outcome.report.verdict,
      details: {
        task_id: outcome.report.taskId,
        filename: selectedFile.value?.name || articleTitle.value || '未命名文章',
        media_type: outcome.report.mediaType,
        verdict: outcome.report.verdict,
        risk_level: outcome.report.riskLevel,
        confidence: outcome.report.confidence,
        summary: outcome.report.summary
      }
    })
  } catch (error) {
    taskError.value = error.message || '检测失败，请稍后重试'
  } finally {
    taskLoading.value = false
  }
}

const formatFileSize = (size) => {
  if (!size) return '0 KB'
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

const handleLogout = async () => {
  authStore.logout()
  await navigateWithoutTransition(router, '/login')
}

const handleEscape = (event) => {
  if (event.key !== 'Escape') return
  if (showImagePreview.value) {
    showImagePreview.value = false
    return
  }
  if (showHistory.value) showHistory.value = false
}

onMounted(() => {
  historyStore.loadHistory()
  window.addEventListener('keydown', handleEscape)
  refreshServiceReadiness(true)
})

onBeforeUnmount(() => {
  dashboardDisposed = true
  if (readinessTimer) clearTimeout(readinessTimer)
  releasePreview()
  window.removeEventListener('keydown', handleEscape)
})
</script>

<style lang="scss" scoped>
.dashboard {
  height: 100vh;
  color: #f2f0e9;
  background: #090d0f;
  overflow-y: auto;
}

.demo-mode-badge {
  padding: 6px 10px;
  color: #9bead6;
  border: 1px solid rgba(80, 211, 196, 0.28);
  border-radius: 999px;
  background: rgba(24, 131, 114, 0.14);
  font-size: 0.72rem;
  font-weight: 760;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

@media (max-width: 760px) {
  .demo-mode-badge {
    display: none;
  }
}

.dashboard.is-workspace {
  background:
    radial-gradient(circle at 12% 10%, rgba(64, 111, 148, 0.1), transparent 34%),
    radial-gradient(circle at 88% 22%, rgba(63, 121, 151, 0.045), transparent 28%),
    linear-gradient(rgba(134, 169, 194, 0.018) 1px, transparent 1px),
    linear-gradient(90deg, rgba(134, 169, 194, 0.018) 1px, transparent 1px),
    linear-gradient(145deg, #07111d 0%, #091827 48%, #07121f 100%);
  background-size: auto, auto, 48px 48px, 48px 48px, auto;
  background-attachment: fixed;
}

.is-workspace .app-header {
  border-bottom: 1px solid rgba(117, 151, 177, 0.08);
  background: linear-gradient(180deg, rgba(6, 15, 26, 0.98), rgba(7, 17, 29, 0.94));
  box-shadow: 0 12px 36px rgba(1, 7, 15, 0.2);
  backdrop-filter: blur(24px) saturate(112%);
}

.app-header {
  min-height: 70px;
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 0 30px;
  border-bottom: 0;
  background: linear-gradient(180deg, rgba(6, 13, 23, 0.9), rgba(8, 17, 29, 0.74));
  box-shadow: 0 14px 42px rgba(0, 0, 0, 0.12);
  backdrop-filter: blur(24px) saturate(135%);
}

.app-header::after {
  content: '';
  position: absolute;
  right: 3%;
  bottom: 0;
  left: 3%;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(106, 170, 215, 0.07) 20%,
    rgba(105, 185, 255, 0.12) 50%,
    rgba(106, 170, 215, 0.07) 80%,
    transparent
  );
  pointer-events: none;
}

.is-home .app-header {
  position: fixed;
  width: 100%;
  background: linear-gradient(180deg, rgba(6, 14, 26, 0.92), rgba(7, 16, 29, 0.58) 68%, rgba(7, 16, 29, 0.08));
  box-shadow: none;
}

.is-home .app-header::after {
  opacity: 0.55;
}

button {
  font: inherit;
}

.brand,
.brand-copy,
.header-actions,
.header-button,
.logout-button,
.secondary-button,
.back-home,
.file-identity,
.control-footer,
.history-header {
  display: flex;
  align-items: center;
}

.brand {
  gap: 0;
  min-height: 38px;
  margin-left: -8px;
  padding: 0 8px;
  border: 0;
  border-radius: 10px;
  color: inherit;
  background: transparent;
  cursor: pointer;
}

.brand-copy {
  align-items: baseline;
  gap: 11px;
  view-transition-name: zhulong-wordmark;
}

.brand-copy strong {
  display: inline-block;
  color: transparent;
  background: linear-gradient(180deg, #fff4c9 0%, #f7d77e 48%, #dfa94e 100%);
  background-clip: text;
  -webkit-background-clip: text;
  filter:
    drop-shadow(0 0 8px rgba(235, 174, 75, 0.22))
    drop-shadow(0 4px 10px rgba(0, 0, 0, 0.32));
  font-size: 1.22rem;
  font-weight: 900;
  line-height: 1;
  letter-spacing: 0.1em;
}

.brand-copy small {
  color: rgba(98, 169, 216, 0.82);
  font-size: 0.68rem;
  font-weight: 680;
  letter-spacing: 0.07em;
}

.header-actions {
  justify-content: flex-end;
  gap: 8px;
}

.header-button,
.logout-button {
  justify-content: center;
  gap: 6px;
  min-height: 36px;
  border-radius: 999px;
  padding: 0 13px;
  cursor: pointer;
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.025em;
  transition: color 160ms ease, border-color 160ms ease, background-color 160ms ease;
}

.secondary-button,
.back-home {
  justify-content: center;
  gap: 7px;
  min-height: 38px;
  border-radius: 10px;
  padding: 0 12px;
  cursor: pointer;
  font-weight: 760;
}

.header-button {
  border: 1px solid rgba(130, 189, 226, 0.12);
  color: rgba(230, 241, 248, 0.84);
  background: rgba(80, 143, 186, 0.065);
}

.secondary-button {
  border: 1px solid rgba(170, 216, 219, 0.16);
  color: #e8eeeb;
  background: rgba(255, 255, 255, 0.055);
}

.logout-button {
  border: 0;
  color: rgba(126, 190, 209, 0.76);
  background: transparent;
}

.back-home {
  border: 0;
  color: #83c9c8;
  background: transparent;
}

.header-button:hover {
  border-color: rgba(129, 199, 239, 0.24);
  color: #f4fbff;
  background: rgba(86, 157, 204, 0.11);
}

.secondary-button:hover {
  border-color: rgba(122, 196, 196, 0.42);
  background: rgba(255, 255, 255, 0.09);
}

.logout-button:hover {
  color: #a9d9e7;
  background: rgba(91, 166, 195, 0.07);
}

.back-home:hover {
  color: #a9e2df;
  background: rgba(115, 198, 198, 0.08);
}

.user-name {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 5px;
  color: rgba(201, 218, 228, 0.58);
  font-size: 0.74rem;
  font-weight: 620;
  letter-spacing: 0.025em;
}

.user-name::before {
  content: '';
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #5da9ca;
  box-shadow: 0 0 9px rgba(93, 169, 202, 0.42);
}

.file-input,
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.home-main {
  min-height: 100vh;
  position: relative;
  display: grid;
  place-items: center;
  padding: 104px 24px 52px;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% -10%, rgba(236, 188, 91, 0.07), transparent 34%),
    radial-gradient(circle at 50% 108%, rgba(32, 111, 207, 0.18), transparent 48%),
    linear-gradient(180deg, #0b1422 0%, #09111d 52%, #0a1626 100%);
}

.home-vignette {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(rgba(255, 255, 255, 0.012) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.012) 1px, transparent 1px),
    radial-gradient(circle at 50% 50%, transparent 15%, rgba(4, 12, 23, 0.34) 92%);
  background-size: 44px 44px, 44px 44px, auto;
  mask-image: linear-gradient(to bottom, transparent, #000 18%, #000 80%, transparent);
  pointer-events: none;
}

.ambient-light {
  position: absolute;
  border-radius: 50%;
  filter: blur(110px);
  opacity: 0.21;
  pointer-events: none;
  animation: ambient-pulse 8s ease-in-out infinite alternate;
}

.ambient-violet {
  width: 430px;
  height: 430px;
  top: -150px;
  left: 17%;
  background: #3b82f6;
}

.ambient-indigo {
  width: 480px;
  height: 480px;
  right: 13%;
  bottom: -230px;
  background: #1d70d8;
  animation-delay: 1.2s;
}

.ambient-fuchsia {
  width: 280px;
  height: 280px;
  top: 30%;
  right: 22%;
  background: #06b6d4;
  opacity: 0.14;
  animation-delay: 2.4s;
}

.ambient-ember {
  width: 260px;
  height: 260px;
  top: -110px;
  left: calc(50% - 130px);
  background: #e2ae4d;
  opacity: 0.08;
  animation-delay: 0.6s;
}

@keyframes ambient-pulse {
  from { transform: scale(0.9); opacity: 0.15; }
  to { transform: scale(1.08); opacity: 0.25; }
}

.hero {
  width: min(760px, 100%);
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.hero-title {
  display: grid;
  justify-items: center;
  gap: 14px;
}

.hero h1 {
  margin: 0;
  color: transparent;
  background: linear-gradient(105deg, #ffffff 5%, rgba(221, 238, 255, 0.78) 100%);
  background-clip: text;
  font-size: clamp(2rem, 4.2vw, 3.05rem);
  font-weight: 570;
  line-height: 1.15;
  letter-spacing: -0.045em;
  text-shadow: 0 18px 48px rgba(0, 0, 0, 0.34);
}

.hero-title > span {
  width: min(290px, 68vw);
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(105, 180, 255, 0.44), transparent);
}

.hero > p:not(.service-readiness) {
  max-width: 650px;
  margin: 10px auto 36px;
  color: rgba(225, 238, 249, 0.58);
  font-size: 0.82rem;
  line-height: 1.8;
}

.composer-wrap {
  width: min(680px, 100%);
  position: relative;
  padding: 4px;
  border-radius: 22px;
  transition: background 180ms ease, transform 180ms ease;
}

.composer-wrap.dragging {
  background: rgba(59, 130, 246, 0.18);
  transform: scale(1.008);
}

.home-notice {
  margin: 9px 0 0 !important;
  color: #8ec9ff !important;
  font-size: 0.78rem !important;
}

.quick-actions {
  width: min(540px, 100%);
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-items: center;
  gap: 7px;
  margin-top: 24px;
}

.quick-actions button {
  min-height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 14px;
  border: 1px solid rgba(176, 215, 250, 0.11);
  border-radius: 10px;
  color: rgba(232, 243, 252, 0.65);
  background: rgba(119, 182, 235, 0.045);
  cursor: pointer;
  backdrop-filter: blur(18px);
  transition: color 160ms ease, background 160ms ease, border-color 160ms ease, transform 160ms ease;
}

.quick-actions button:hover {
  border-color: rgba(99, 175, 244, 0.34);
  color: #f5fbff;
  background: rgba(74, 151, 222, 0.11);
  transform: translateY(-2px);
}

.quick-actions button svg {
  color: #69b9ff;
}

.quick-actions button span {
  font-size: 0.74rem;
  font-weight: 750;
}

.service-readiness {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 18px 0 0 !important;
  color: rgba(211, 230, 244, 0.58) !important;
  font-size: 0.68rem !important;
}

.service-readiness span {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: #7b8791;
  box-shadow: 0 0 0 4px rgba(123, 135, 145, 0.1);
}

.service-readiness.is-ready {
  color: rgba(166, 232, 202, 0.76) !important;
}

.service-readiness.is-ready span {
  background: #58d49e;
  box-shadow: 0 0 0 4px rgba(88, 212, 158, 0.1), 0 0 12px rgba(88, 212, 158, 0.38);
}

.service-readiness.is-partial {
  color: rgba(247, 204, 126, 0.76) !important;
}

.service-readiness.is-partial span,
.service-readiness.is-checking span {
  background: #e5b75c;
  box-shadow: 0 0 0 4px rgba(229, 183, 92, 0.1);
}

.service-readiness.is-unavailable {
  color: rgba(245, 151, 151, 0.76) !important;
}

.service-readiness.is-unavailable span {
  background: #e87373;
  box-shadow: 0 0 0 4px rgba(232, 115, 115, 0.1);
}

.app-main {
  width: min(1320px, calc(100% - 48px));
  margin: 0 auto;
  padding: 30px 0 56px;
}

.page-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 28px;
  margin-bottom: 24px;
}

.back-home {
  min-height: 30px;
  margin: 0 0 7px -8px;
  padding: 0 8px;
  font-size: 0.74rem;
}

.eyebrow,
.section-heading span,
.control-heading > span,
.history-header span,
.result-toolbar span,
.capability-list > span {
  color: #70bdbc;
  font-size: 0.7rem;
  font-weight: 900;
  letter-spacing: 0.12em;
}

.page-heading h1 {
  margin: 3px 0 4px;
  color: #f5f2e9;
  font-size: 1.75rem;
  line-height: 1.2;
}

.page-heading p:last-child {
  color: #939e9c;
  font-size: 0.88rem;
}

.flow-steps {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.flow-steps li {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 10px;
  border: 1px solid #2c3639;
  border-radius: 9px;
  color: #75807f;
  font-size: 0.74rem;
  font-weight: 800;
  white-space: nowrap;
}

.flow-steps li span {
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: #222a2d;
  font-size: 0.66rem;
}

.flow-steps li.active {
  border-color: #89743f;
  color: #efd584;
  background: #211f18;
}

.flow-steps li.completed { color: #86ceca; }
.flow-steps li.completed span { background: #214d4c; }

.analysis-workspace {
  min-height: 610px;
  display: grid;
  grid-template-columns: minmax(0, 1.42fr) minmax(360px, 0.72fr);
  border: 1px solid #293336;
  border-radius: 16px;
  background: #101618;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.2);
  overflow: hidden;
}

.media-column,
.article-editor-column,
.control-column {
  min-width: 0;
  padding: 24px;
}

.control-column {
  border-left: 1px solid #293336;
  background: #141b1e;
}

.section-heading {
  min-height: 54px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 16px;
}

.section-heading small {
  color: #788483;
  font-size: 0.74rem;
}

.article-editor-card {
  display: grid;
  gap: 18px;
  padding: 20px;
  border: 1px solid #303c40;
  border-radius: 12px;
  background:
    linear-gradient(145deg, rgba(114, 192, 190, 0.035), transparent 42%),
    #0b1113;
}

.article-field {
  display: grid;
  gap: 8px;
}

.article-field > span {
  color: #aab5b1;
  font-size: 0.75rem;
  font-weight: 750;
}

.article-field input,
.article-field textarea {
  width: 100%;
  border: 1px solid #303c40;
  border-radius: 9px;
  outline: 0;
  color: #e6ebe8;
  background: #101719;
  font: inherit;
  transition: border-color 160ms ease, box-shadow 160ms ease;
}

.article-field input {
  min-height: 42px;
  padding: 0 12px;
}

.article-field textarea {
  min-height: 300px;
  padding: 14px;
  resize: vertical;
  line-height: 1.75;
}

.article-field input:focus,
.article-field textarea:focus {
  border-color: rgba(126, 200, 198, 0.6);
  box-shadow: 0 0 0 3px rgba(73, 159, 158, 0.09);
}

.article-field input::placeholder,
.article-field textarea::placeholder {
  color: #5f6b69;
}

.article-origin-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.article-origin-grid .article-field:first-child {
  grid-column: 1 / -1;
}

.article-offline-note {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 0;
  padding: 11px 12px;
  border: 1px solid rgba(229, 196, 111, 0.15);
  border-radius: 9px;
  color: #b8ae8d;
  background: rgba(229, 196, 111, 0.045);
  font-size: 0.75rem;
  line-height: 1.55;
}

.article-offline-note svg {
  flex: 0 0 auto;
  margin-top: 2px;
}

.section-heading h2,
.control-heading h2,
.history-header h2 {
  margin: 2px 0 0;
  font-size: 1.1rem;
}

.text-button {
  min-height: 36px;
  border: 0;
  color: #88cecb;
  background: transparent;
  padding: 0 6px;
  cursor: pointer;
  font-weight: 800;
}

.dropzone {
  height: 430px;
  display: grid;
  place-items: center;
  border: 1px solid #303c40;
  border-radius: 12px;
  background:
    linear-gradient(rgba(255, 255, 255, 0.018) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.018) 1px, transparent 1px),
    #0a0f11;
  background-size: 28px 28px;
  overflow: hidden;
  transition: border-color 160ms ease, box-shadow 160ms ease;
}

.dropzone.dragging {
  border-color: #d9bb68;
  box-shadow: inset 0 0 0 3px rgba(229, 196, 111, 0.08);
}

.media-preview {
  width: 100%;
  height: 100%;
  position: relative;
  margin: 0;
  display: grid;
  place-items: center;
}

.media-preview img,
.media-preview video {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: contain;
}

.media-preview video {
  background: #050809;
}

.analyzing-overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgba(5, 10, 12, 0.56);
  backdrop-filter: blur(2px);
}

.analyzing-overlay span {
  width: 70%;
  height: 2px;
  align-self: center;
  background: #e5c46f;
  box-shadow: 0 0 24px rgba(229, 196, 111, 0.76);
  animation: scan 2.2s ease-in-out infinite;
}

.analyzing-overlay small {
  position: absolute;
  bottom: 24px;
  color: rgba(244, 235, 207, 0.78);
  font-size: 0.75rem;
  letter-spacing: 0.08em;
}

@keyframes scan {
  0%, 100% { transform: translateY(-150px); opacity: 0.35; }
  50% { transform: translateY(150px); opacity: 1; }
}

.file-summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 20px;
  align-items: center;
  margin-top: 14px;
}

.file-identity {
  min-width: 0;
  gap: 10px;
}

.file-identity > div {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.file-type-icon {
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border-radius: 9px;
  color: #e8c970;
  background: rgba(229, 196, 111, 0.09);
}

.file-type-icon.video {
  color: #83cfcc;
  background: rgba(105, 194, 192, 0.09);
}

.file-summary strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-summary span,
.file-summary dt {
  color: #879392;
  font-size: 0.75rem;
}

.file-summary dl {
  display: flex;
  gap: 22px;
  margin: 0;
}

.file-summary dl div { display: grid; gap: 2px; }
.file-summary dd { margin: 0; color: #d4dad7; font-size: 0.8rem; }

.control-heading {
  display: grid;
  gap: 2px;
}

.control-heading p,
.source-description {
  color: #919c9a;
  font-size: 0.83rem;
  line-height: 1.65;
}

.control-heading p { margin-top: 5px; }

.task-intention {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 10px;
  margin-top: 18px;
  padding: 12px;
  border: 1px solid rgba(117, 198, 197, 0.13);
  border-radius: 10px;
  color: #7ec8c6;
  background: rgba(61, 137, 138, 0.055);
}

.task-intention span { color: #73b9b8; font-size: 0.68rem; font-weight: 850; }
.task-intention p { margin-top: 3px; color: #c5ceca; font-size: 0.78rem; line-height: 1.55; }

.source-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 20px 0 0;
  padding: 0;
  border: 0;
}

.source-options label {
  min-height: 42px;
  display: grid;
  place-items: center;
  border: 1px solid #334044;
  border-radius: 9px;
  color: #abb4b2;
  background: #0e1416;
  cursor: pointer;
  font-size: 0.78rem;
  font-weight: 800;
}

.source-options label:last-child { grid-column: 1 / -1; }
.source-options label.selected { border-color: #957e44; color: #efd483; background: #211f18; }
.source-options label:focus-within { outline: 2px solid #72bcbc; outline-offset: 2px; }
.source-options input { position: absolute; opacity: 0; pointer-events: none; }

.source-description {
  min-height: 58px;
  margin: 10px 0 0;
  padding: 11px 12px;
  border-left: 2px solid #4b8584;
  background: #101719;
}

.capability-list {
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid #2a3437;
}

.capability-list ul {
  display: grid;
  gap: 8px;
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}

.capability-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #bcc5c1;
  font-size: 0.78rem;
}

.capability-list li svg { color: #78c5c2; }

.error-message {
  margin-top: 14px;
  padding: 11px 12px;
  border: 1px solid #704642;
  border-radius: 9px;
  color: #efaaa3;
  background: #241818;
  font-size: 0.82rem;
}

.control-footer {
  justify-content: space-between;
  gap: 14px;
  margin-top: 21px;
}

.control-footer small { max-width: 185px; color: #737f7d; font-size: 0.68rem; line-height: 1.5; }

.primary-button {
  min-width: 134px;
  min-height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid #e5c46f;
  border-radius: 10px;
  color: #161713;
  background: #e5c46f;
  cursor: pointer;
  font-weight: 850;
}

.primary-button:hover { background: #efd486; }

.result-workspace { border-top: 1px solid rgba(119, 159, 190, 0.12); }
.result-toolbar {
  min-height: 62px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 12px;
  padding: 0 4px;
}
.result-toolbar > div { min-width: 0; display: flex; align-items: center; gap: 10px; }
.result-toolbar strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #dcecff; font-size: 0.82rem; }

.is-workspace .page-heading h1 {
  color: #e5edf3;
}

.is-workspace .page-heading p:last-child {
  color: rgba(188, 204, 217, 0.62);
}

.is-workspace .eyebrow,
.is-report .result-toolbar span {
  color: #73a8c5;
}

.is-workspace .flow-steps li {
  border-color: rgba(126, 160, 187, 0.13);
  color: rgba(174, 193, 207, 0.5);
  background: rgba(17, 38, 58, 0.38);
}

.is-workspace .flow-steps li span {
  background: rgba(80, 125, 159, 0.16);
}

.is-workspace .flow-steps li.completed,
.is-workspace .flow-steps li.active {
  border-color: rgba(102, 163, 200, 0.32);
  color: #b9d3e2;
  background: rgba(42, 91, 126, 0.24);
}

.is-workspace .flow-steps li.completed span,
.is-workspace .flow-steps li.active span {
  background: #376f94;
}

.is-report .secondary-button {
  border-color: rgba(116, 162, 194, 0.18);
  color: #d2e0e9;
  background: rgba(37, 78, 108, 0.18);
}

.history-overlay {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: flex;
  justify-content: flex-end;
  padding: 14px;
  background: rgba(3, 7, 9, 0.72);
  backdrop-filter: blur(9px);
}

.history-panel {
  width: min(450px, 100%);
  display: flex;
  flex-direction: column;
  padding: 20px;
  border: 1px solid #334043;
  border-radius: 16px;
  background: #12191b;
  box-shadow: -22px 0 80px rgba(0, 0, 0, 0.32);
  overflow: hidden;
}

.history-header { justify-content: space-between; gap: 14px; margin-bottom: 18px; }

.close-button {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border: 1px solid #344043;
  border-radius: 10px;
  color: #bcc5c1;
  background: #182023;
  cursor: pointer;
}

@media (max-width: $tablet) {
  .page-heading { align-items: flex-start; flex-direction: column; }
  .analysis-workspace { grid-template-columns: 1fr; }
  .control-column { border-top: 1px solid #293336; border-left: 0; }
  .dropzone { height: 390px; }
}

@media (max-width: $mobile) {
  .app-header { min-height: 60px; padding: 0 14px; }
  .brand-copy small, .user-name, .logout-button span { display: none; }
  .header-actions { gap: 4px; }
  .header-button { min-height: 36px; padding: 0 9px; }
  .logout-button { width: 36px; padding: 0; }

  .home-main { align-items: start; min-height: 100svh; padding: 116px 14px 34px; }
  .hero h1 { font-size: clamp(1.9rem, 9.5vw, 2.5rem); }
  .hero > p:not(.service-readiness) { margin: 10px auto 27px; font-size: 0.76rem; }
  .quick-actions { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; margin-top: 18px; }
  .quick-actions button { min-width: 0; min-height: 42px; justify-content: center; padding: 0 8px; }
  .quick-actions button:last-child {
    width: calc((100% - 7px) / 2);
    grid-column: 1 / -1;
    justify-self: center;
  }

  .app-main { width: calc(100% - 28px); padding: 21px 0 38px; }
  .page-heading { gap: 17px; margin-bottom: 18px; }
  .page-heading h1 { font-size: 1.4rem; }
  .flow-steps { width: 100%; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 5px; }
  .flow-steps li { min-width: 0; justify-content: center; padding: 0 4px; font-size: 0; }
  .flow-steps li span { font-size: 0.66rem; }
  .analysis-workspace { min-height: 0; border-radius: 12px; }
  .media-column, .article-editor-column, .control-column { padding: 15px; }
  .article-editor-card { padding: 14px; }
  .article-origin-grid { grid-template-columns: 1fr; }
  .article-origin-grid .article-field:first-child { grid-column: auto; }
  .article-field textarea { min-height: 260px; }
  .dropzone { height: 310px; }
  .file-summary { grid-template-columns: minmax(0, 1fr); }
  .file-summary dl { justify-content: space-between; }
  .control-footer { align-items: stretch; flex-direction: column; }
  .control-footer small { max-width: none; }
  .primary-button { width: 100%; }
  .result-toolbar > div { display: none; }
  .result-toolbar { justify-content: flex-end; }
}

@media (prefers-reduced-motion: reduce) {
  .analyzing-overlay span { animation: none; }
  .ambient-light { animation: none; }
  .quick-actions button, .composer-wrap { transition: none; }
}

/* Low-luminance navy workspace: aligned with the navigation shell. */
.is-workspace .analysis-workspace {
  border-color: rgba(118, 157, 186, 0.15);
  background:
    radial-gradient(circle at 4% 0%, rgba(69, 119, 155, 0.07), transparent 32%),
    linear-gradient(145deg, rgba(11, 27, 43, 0.97), rgba(7, 19, 32, 0.98));
  box-shadow:
    inset 0 1px 0 rgba(202, 221, 235, 0.055),
    0 30px 90px rgba(1, 7, 16, 0.26);
}

.is-workspace .media-column,
.is-workspace .article-editor-column {
  background: rgba(8, 24, 39, 0.26);
}

.is-workspace .control-column {
  border-left-color: rgba(120, 158, 185, 0.12);
  background:
    linear-gradient(155deg, rgba(61, 104, 137, 0.07), transparent 48%),
    rgba(10, 27, 44, 0.72);
}

.is-workspace .section-heading span,
.is-workspace .control-heading > span,
.is-workspace .capability-list > span {
  color: #6fa8c7;
}

.is-workspace .section-heading h2,
.is-workspace .control-heading h2 {
  color: #e3ebf0;
}

.is-workspace .section-heading small,
.is-workspace .control-heading p {
  color: rgba(181, 199, 213, 0.57);
}

.is-workspace .text-button {
  color: #78acc8;
}

.is-workspace .text-button:hover {
  color: #b9d5e3;
  background: rgba(74, 121, 154, 0.1);
}

.is-workspace .article-editor-card {
  border-color: rgba(120, 158, 185, 0.13);
  background:
    linear-gradient(145deg, rgba(69, 112, 145, 0.05), transparent 42%),
    rgba(7, 23, 38, 0.62);
  box-shadow: inset 0 1px 0 rgba(202, 221, 235, 0.035);
}

.is-workspace .article-field > span {
  color: rgba(201, 214, 224, 0.7);
}

.is-workspace .article-field input,
.is-workspace .article-field textarea {
  border-color: rgba(120, 158, 185, 0.12);
  color: #e1e9ef;
  background: rgba(6, 19, 32, 0.72);
}

.is-workspace .article-field input:focus,
.is-workspace .article-field textarea:focus {
  border-color: rgba(99, 158, 194, 0.5);
  box-shadow: 0 0 0 4px rgba(66, 118, 153, 0.1);
}

.is-workspace .article-field input::placeholder,
.is-workspace .article-field textarea::placeholder {
  color: rgba(160, 181, 197, 0.36);
}

.is-workspace .article-offline-note {
  border-color: rgba(111, 157, 189, 0.13);
  color: rgba(181, 202, 216, 0.64);
  background: rgba(42, 82, 111, 0.09);
}

.is-workspace .dropzone {
  height: clamp(390px, 56vh, 620px);
  min-height: 0;
  position: relative;
  border-color: rgba(119, 157, 185, 0.14);
  background:
    linear-gradient(rgba(132, 169, 194, 0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(132, 169, 194, 0.02) 1px, transparent 1px),
    radial-gradient(circle at 50% 48%, rgba(55, 103, 139, 0.07), transparent 52%),
    rgba(5, 18, 31, 0.68);
  background-size: 28px 28px, 28px 28px, auto, auto;
  box-shadow:
    inset 0 1px 0 rgba(202, 221, 235, 0.035),
    0 18px 48px rgba(1, 8, 18, 0.16);
}

.is-workspace .dropzone.preview-portrait {
  height: clamp(500px, 68vh, 720px);
}

.is-workspace .dropzone.preview-wide {
  height: clamp(330px, 47vh, 520px);
}

.is-workspace .dropzone.dragging {
  border-color: rgba(103, 166, 202, 0.62);
  box-shadow:
    inset 0 0 0 3px rgba(75, 130, 165, 0.1),
    0 0 36px rgba(48, 105, 140, 0.1);
}

.media-preview {
  min-width: 0;
  min-height: 0;
  padding: 18px;
  overflow: hidden;
}

.media-preview img {
  width: 100%;
  height: 100%;
  max-width: 100%;
  max-height: 100%;
  min-width: 0;
  min-height: 0;
  display: block;
  object-fit: contain;
  object-position: center;
}

.media-preview video {
  width: 100%;
  height: 100%;
  max-width: 100%;
  max-height: 100%;
  min-width: 0;
  min-height: 0;
  display: block;
  border-radius: 8px;
  background: rgba(2, 10, 18, 0.82);
  object-fit: contain;
  object-position: center;
}

.preview-expand {
  position: absolute;
  right: 14px;
  bottom: 14px;
  z-index: 3;
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 11px;
  border: 1px solid rgba(143, 178, 201, 0.2);
  border-radius: 9px;
  color: #d8e4eb;
  background: rgba(7, 24, 39, 0.9);
  box-shadow: 0 10px 28px rgba(0, 9, 24, 0.28);
  backdrop-filter: blur(14px);
  cursor: pointer;
  font-size: 0.72rem;
  font-weight: 760;
}

.preview-expand:hover {
  border-color: rgba(111, 166, 198, 0.42);
  background: rgba(18, 52, 75, 0.94);
}

.is-workspace .analyzing-overlay {
  background: rgba(4, 17, 30, 0.74);
  backdrop-filter: blur(3px);
}

.is-workspace .analyzing-overlay span {
  background: #69a9c9;
  box-shadow: 0 0 22px rgba(83, 149, 184, 0.5);
}

.is-workspace .analyzing-overlay small {
  color: rgba(207, 222, 231, 0.8);
}

.is-workspace .file-summary {
  padding: 14px;
  border: 1px solid rgba(120, 158, 185, 0.11);
  border-radius: 11px;
  background: rgba(32, 66, 91, 0.1);
}

.is-workspace .file-type-icon {
  color: #82b3cc;
  background: rgba(56, 111, 148, 0.15);
}

.is-workspace .file-type-icon.video {
  color: #8be3dc;
  background: rgba(38, 160, 156, 0.13);
}

.is-workspace .file-summary strong,
.is-workspace .file-summary dd {
  color: #dce6ec;
}

.is-workspace .file-summary span,
.is-workspace .file-summary dt {
  color: rgba(173, 194, 209, 0.54);
}

.is-workspace .task-intention {
  border-color: rgba(105, 157, 190, 0.14);
  color: #79abc7;
  background: rgba(42, 84, 114, 0.1);
}

.is-workspace .task-intention span {
  color: #75a9c5;
}

.is-workspace .task-intention p {
  color: rgba(204, 216, 225, 0.7);
}

.is-workspace .source-options label {
  border-color: rgba(120, 158, 185, 0.12);
  color: rgba(197, 211, 221, 0.66);
  background: rgba(8, 25, 41, 0.62);
}

.is-workspace .source-options label:hover {
  border-color: rgba(103, 163, 198, 0.28);
  color: #dfe9ef;
  background: rgba(35, 75, 104, 0.24);
}

.is-workspace .source-options label.selected {
  border-color: rgba(98, 161, 199, 0.46);
  color: #bdd5e2;
  background: rgba(43, 88, 119, 0.28);
  box-shadow: inset 0 0 0 1px rgba(109, 170, 204, 0.06);
}

.is-workspace .source-options label:focus-within {
  outline-color: #6da3bf;
}

.is-workspace .source-description {
  border-left-color: #568cab;
  color: rgba(183, 202, 216, 0.62);
  background: rgba(37, 73, 99, 0.13);
}

.is-workspace .capability-list {
  border-top-color: rgba(120, 158, 185, 0.11);
}

.is-workspace .capability-list li {
  color: rgba(205, 217, 225, 0.7);
}

.is-workspace .capability-list li svg {
  color: #6fa6c3;
}

.is-workspace .control-footer small {
  color: rgba(163, 184, 199, 0.46);
}

.is-workspace .primary-button {
  border-color: rgba(121, 172, 201, 0.68);
  color: #f1f6f8;
  background: linear-gradient(135deg, #5c96b6, #437b9d);
  box-shadow: 0 12px 30px rgba(32, 86, 119, 0.2);
}

.is-workspace .primary-button:hover {
  background: linear-gradient(135deg, #6aa2c0, #5189a8);
  transform: translateY(-1px);
}

.history-overlay {
  background: rgba(2, 9, 17, 0.76);
}

.history-panel {
  border-color: rgba(120, 158, 185, 0.15);
  background:
    radial-gradient(circle at 80% 0%, rgba(67, 115, 149, 0.08), transparent 34%),
    linear-gradient(160deg, rgba(11, 29, 46, 0.99), rgba(6, 18, 31, 0.99));
  box-shadow:
    -22px 0 80px rgba(0, 5, 13, 0.38),
    inset 0 1px 0 rgba(202, 221, 235, 0.05);
}

.close-button {
  border-color: rgba(120, 158, 185, 0.14);
  color: #cbdbe4;
  background: rgba(43, 80, 106, 0.17);
}

.image-lightbox {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: grid;
  place-items: center;
  padding: 28px;
  background:
    radial-gradient(circle at 50% 42%, rgba(30, 104, 170, 0.2), transparent 48%),
    rgba(2, 12, 27, 0.93);
  backdrop-filter: blur(18px);
}

.image-lightbox figure {
  width: min(1180px, 100%);
  height: min(86vh, 860px);
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  margin: 0;
  padding: 18px;
  border: 1px solid rgba(124, 190, 255, 0.2);
  border-radius: 16px;
  background: rgba(7, 31, 61, 0.78);
  box-shadow:
    0 36px 120px rgba(0, 5, 18, 0.55),
    inset 0 1px 0 rgba(205, 235, 255, 0.08);
}

.image-lightbox img {
  width: 100%;
  height: 100%;
  max-width: 100%;
  max-height: 100%;
  min-width: 0;
  min-height: 0;
  display: block;
  object-fit: contain;
  object-position: center;
}

.image-lightbox figcaption {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 15px 4px 0;
  color: rgba(183, 214, 238, 0.58);
  font-size: 0.75rem;
}

.image-lightbox figcaption strong {
  overflow: hidden;
  color: #edf8ff;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lightbox-close {
  width: 42px;
  height: 42px;
  position: fixed;
  top: 22px;
  right: 22px;
  z-index: 1;
  display: grid;
  place-items: center;
  border: 1px solid rgba(143, 207, 255, 0.23);
  border-radius: 11px;
  color: #e6f5ff;
  background: rgba(12, 54, 91, 0.78);
  cursor: pointer;
}

.preview-fade-enter-active,
.preview-fade-leave-active {
  transition: opacity 160ms ease;
}

.preview-fade-enter-from,
.preview-fade-leave-to {
  opacity: 0;
}

.dashboard::-webkit-scrollbar-thumb {
  background: rgba(74, 122, 153, 0.58);
}

.dashboard::-webkit-scrollbar-thumb:hover {
  background: rgba(91, 145, 176, 0.7);
}

@media (max-width: $tablet) {
  .is-workspace .control-column {
    border-top-color: rgba(124, 190, 255, 0.16);
    border-left: 0;
  }

  .is-workspace .dropzone.preview-portrait {
    height: clamp(460px, 64vh, 650px);
  }
}

@media (max-width: $mobile) {
  .is-workspace .dropzone,
  .is-workspace .dropzone.preview-standard {
    height: clamp(300px, 48vh, 430px);
  }

  .is-workspace .dropzone.preview-portrait {
    height: clamp(420px, 62vh, 560px);
  }

  .is-workspace .dropzone.preview-wide {
    height: clamp(260px, 38vh, 340px);
  }

  .media-preview {
    padding: 10px;
  }

  .preview-expand {
    right: 10px;
    bottom: 10px;
  }

  .image-lightbox {
    padding: 12px;
  }

  .image-lightbox figure {
    height: min(84vh, 760px);
    padding: 10px;
  }

  .image-lightbox figcaption {
    align-items: flex-start;
    flex-direction: column;
    gap: 3px;
    padding: 11px 2px 2px;
  }

  .lightbox-close {
    top: 16px;
    right: 16px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .preview-fade-enter-active,
  .preview-fade-leave-active,
  .is-workspace .primary-button {
    transition: none;
  }
}

/* Desktop single-screen workbench. */
@media (min-width: 1025px) and (min-height: 720px) {
  .dashboard.is-workspace {
    overflow: hidden;
  }

  .is-workspace .app-main {
    height: calc(100svh - 70px);
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
    padding: 12px 0 16px;
    overflow: hidden;
  }

  .is-workspace .page-heading {
    min-height: 60px;
    align-items: center;
    margin-bottom: 10px;
  }

  .is-workspace .back-home {
    min-height: 24px;
    margin-bottom: 2px;
  }

  .is-workspace .eyebrow {
    display: none;
  }

  .is-workspace .page-heading h1 {
    margin: 0;
    font-size: 1.35rem;
  }

  .is-workspace .page-heading p:last-child {
    display: none;
  }

  .is-workspace .flow-steps li {
    min-height: 30px;
    padding: 0 9px;
    font-size: 0.69rem;
  }

  .is-workspace .analysis-workspace {
    min-height: 0;
    height: 100%;
  }

  .is-workspace .media-column {
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: 16px;
    overflow: hidden;
  }

  .is-workspace .article-editor-column {
    min-height: 0;
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
    padding: 16px;
    overflow: hidden;
  }

  .is-workspace .control-column {
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: 16px;
    overflow: auto;
  }

  .is-workspace .section-heading {
    min-height: 38px;
    margin-bottom: 8px;
  }

  .is-workspace .section-heading h2,
  .is-workspace .control-heading h2 {
    font-size: 1rem;
  }

  .is-workspace .dropzone,
  .is-workspace .dropzone.preview-standard,
  .is-workspace .dropzone.preview-portrait,
  .is-workspace .dropzone.preview-wide {
    min-height: 0;
    height: auto;
    flex: 1 1 auto;
  }

  .is-workspace .media-preview {
    padding: 12px;
  }

  .is-workspace .file-summary {
    flex: 0 0 auto;
    margin-top: 8px;
    padding: 9px 11px;
  }

  .is-workspace .file-type-icon {
    width: 32px;
    height: 32px;
  }

  .is-workspace .file-summary dl {
    gap: 16px;
  }

  .is-workspace .article-editor-card {
    min-height: 0;
    grid-template-rows: auto minmax(150px, 1fr) auto auto;
    gap: 10px;
    padding: 14px;
    overflow: hidden;
  }

  .is-workspace .article-body-field {
    min-height: 0;
    grid-template-rows: auto minmax(0, 1fr);
  }

  .is-workspace .article-field {
    gap: 5px;
  }

  .is-workspace .article-field input {
    min-height: 36px;
  }

  .is-workspace .article-field textarea {
    min-height: 0;
    height: 100%;
    padding: 11px;
  }

  .is-workspace .article-origin-grid {
    grid-template-columns: 1.4fr 0.8fr 0.8fr;
    gap: 10px;
  }

  .is-workspace .article-origin-grid .article-field:first-child {
    grid-column: auto;
  }

  .is-workspace .article-offline-note {
    padding: 7px 9px;
    font-size: 0.69rem;
  }

  .is-workspace .control-heading p {
    margin-top: 3px;
    font-size: 0.75rem;
    line-height: 1.5;
  }

  .is-workspace .task-intention {
    grid-template-columns: auto minmax(0, 1fr);
    gap: 7px;
    margin-top: 10px;
    padding: 8px 9px;
  }

  .is-workspace .task-intention p {
    display: -webkit-box;
    margin-top: 1px;
    overflow: hidden;
    font-size: 0.7rem;
    line-height: 1.4;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 1;
  }

  .is-workspace .source-options {
    gap: 6px;
    margin-top: 12px;
  }

  .is-workspace .source-options label {
    min-height: 34px;
    font-size: 0.72rem;
  }

  .is-workspace .source-description {
    min-height: 0;
    margin-top: 7px;
    padding: 8px 9px;
    font-size: 0.72rem;
    line-height: 1.45;
  }

  .is-workspace .capability-list {
    margin-top: 12px;
    padding-top: 11px;
  }

  .is-workspace .capability-list ul {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 12px;
    margin-top: 7px;
  }

  .is-workspace .capability-list li {
    font-size: 0.71rem;
  }

  .is-workspace .control-footer {
    margin-top: auto;
    padding-top: 12px;
  }

  .is-workspace .primary-button {
    min-height: 38px;
  }

  .is-report .app-main {
    width: min(1040px, calc(100% - 48px));
    height: calc(100svh - 70px);
    min-height: 0;
    grid-template-rows: minmax(0, 1fr);
    padding-bottom: 16px;
    overflow: hidden;
  }

  .dashboard.is-report {
    overflow: hidden;
  }

  .is-report .page-heading {
    display: none;
  }

  .is-report .result-workspace {
    min-height: 0;
    height: 100%;
    display: grid;
    grid-template-rows: 44px minmax(0, 1fr);
    align-content: start;
    border-top: 0;
  }

  .is-report .result-toolbar {
    min-height: 44px;
    margin: 0;
  }

  .is-report .result-workspace > article {
    min-height: 0;
    height: min(626px, 100%);
    max-height: 100%;
    align-self: start;
  }

  .is-report .result-workspace > .article-report {
    height: min(626px, 100%);
    align-self: start;
  }
}

@media (min-width: 1025px) and (max-height: 719px) {
  .dashboard.is-report {
    overflow: hidden;
  }

  .is-report .app-main {
    width: min(1040px, calc(100% - 48px));
    height: calc(100svh - 70px);
    min-height: 0;
    display: grid;
    grid-template-rows: minmax(0, 1fr);
    padding: 8px 0 12px;
    overflow: hidden;
  }

  .is-report .page-heading {
    display: none;
  }

  .is-report .result-workspace {
    min-height: 0;
    height: 100%;
    display: grid;
    grid-template-rows: 38px minmax(0, 1fr);
    align-content: start;
    border-top: 0;
  }

  .is-report .result-toolbar {
    min-height: 38px;
    margin: 0;
  }

  .is-report .result-workspace > article {
    min-height: 0;
    height: min(626px, 100%);
    max-height: 100%;
    align-self: start;
  }
}
</style>
