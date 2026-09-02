<template>
  <div class="history-list">
    <div class="filters">
      <label>
        <span>媒体类型</span>
        <select v-model="selectedType">
          <option value="">全部</option>
          <option value="image">图片</option>
          <option value="video">视频</option>
          <option value="article">AI 文字</option>
        </select>
      </label>
      <label>
        <span>风险等级</span>
        <select v-model="selectedRisk">
          <option value="">全部</option>
          <option value="high">高风险</option>
          <option value="medium">中风险</option>
          <option value="low">低风险</option>
          <option value="unknown">未知</option>
        </select>
      </label>
    </div>

    <div class="content">
      <div v-if="loading" class="state">正在加载记录</div>
      <div v-else-if="filteredHistory.length === 0" class="state">暂无检测历史</div>

      <article v-for="item in filteredHistory" v-else :key="item.id" class="history-item">
        <header>
          <div>
            <strong>{{ typeLabel(item.type) }}</strong>
            <p>{{ item.details?.filename || '媒体文件' }}</p>
          </div>
          <span :class="['risk-pill', item.details?.risk_level || 'unknown']">
            {{ riskLabel(item.details?.risk_level, item.details?.verdict || item.result, item.type) }}
          </span>
        </header>

        <p class="summary">{{ item.details?.summary || verdictLabel(item.details?.verdict || item.result) }}</p>

        <div class="meta">
          <span v-if="item.details?.task_id">{{ item.details.task_id }}</span>
          <span v-if="item.details?.confidence != null">置信度 {{ item.details.confidence }}%</span>
          <span>{{ formatTime(item.time) }}</span>
        </div>

        <button class="delete-button" type="button" @click="deleteItem(item)">删除</button>
      </article>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useHistoryStore } from '@/stores/history'

const historyStore = useHistoryStore()
const selectedType = ref('')
const selectedRisk = ref('')

const loading = computed(() => historyStore.loading)
const history = computed(() => historyStore.history)

const filteredHistory = computed(() => history.value.filter((item) => {
  if (selectedType.value && item.type !== selectedType.value) return false
  if (selectedRisk.value && item.details?.risk_level !== selectedRisk.value) return false
  return true
}))

const typeLabel = (type) => ({
  image: '图片检测',
  video: '视频联合鉴伪',
  article: 'AI 文字检测'
}[type] || '内容核查')

const riskLabel = (level, verdict = '', type = '') => {
  if (verdict === 'failed') return type === 'article' ? '核查失败' : '检测失败'
  if (type === 'article') {
    return ({
      high: '高 AI 风格信号',
      medium: '中 AI 风格信号',
      low: '未见强 AI 信号',
      unknown: '无法确认'
    }[level] || '无法确认')
  }
  if (level === 'unknown' && verdict === 'uncertain') return '无法确认'
  return ({
    high: '高风险',
    medium: '中风险',
    low: '低风险',
    unknown: '未知'
  }[level] || '未知')
}

const verdictLabel = (verdict) => ({
  ai_generated: '检测到较高 AI 生成风险',
  ai_generated_video_suspected: '检测到完整 AI 生成视频信号',
  face_manipulation_suspected: '检测到人脸换脸或操纵信号',
  multiple_video_ai_signals: '检测到多种视频 AI 伪造信号',
  likely_real: '未发现明显 AI 生成风险',
  failed: '检测失败',
  uncertain: '无法形成明确结论',
  ai_style_suspected: '检测到较强 AI 写作风格信号',
  no_strong_ai_signal: '当前未发现一致的强 AI 写作信号',
  insufficient_text: '正文过短，无法稳定分析',
  text_detection_unavailable: '文字模型未完成调用',
  insufficient_evidence: '已生成清单，重要声明尚待外部核验',
  no_checkable_claims: '未提取到适合客观核验的事实声明',
  claim_conflicts_found: '核查范围内发现声明证据冲突',
  supported_within_scope: '本次核查范围内声明获得证据支持'
}[verdict] || '检测完成')

const formatTime = (timeString) => {
  const date = new Date(timeString)
  if (Number.isNaN(date.getTime())) return '未知时间'
  return date.toLocaleString()
}

const deleteItem = async (item) => {
  if (!confirm('确定删除这条检测记录吗？')) return
  await historyStore.deleteRecord(item.id)
}

onMounted(() => {
  historyStore.loadHistory()
})
</script>

<style lang="scss" scoped>
.history-list {
  min-height: 0;
  display: flex;
  flex: 1;
  flex-direction: column;
  color: #e2e9ee;
}

.filters {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

label {
  display: grid;
  gap: 6px;
}

label span {
  color: rgba(190, 205, 216, 0.56);
  font-size: 0.76rem;
  font-weight: 800;
}

select {
  height: 36px;
  border: 1px solid rgba(120, 158, 185, 0.13);
  border-radius: 8px;
  color: #dfe8ed;
  background: rgba(4, 15, 26, 0.78);
  padding: 0 10px;
}

.content {
  min-height: 0;
  overflow-y: auto;
  display: grid;
  gap: 12px;
}

.state {
  min-height: 180px;
  display: grid;
  place-items: center;
  color: rgba(181, 197, 209, 0.54);
}

.history-item {
  position: relative;
  padding: 14px;
  border: 1px solid rgba(120, 158, 185, 0.1);
  border-radius: 8px;
  background: rgba(5, 18, 31, 0.66);
}

.history-item header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.history-item strong {
  color: #e0e8ed;
}

.history-item p {
  margin: 3px 0 0;
  color: rgba(190, 204, 214, 0.59);
  font-size: 0.84rem;
}

.summary {
  margin-top: 10px !important;
  line-height: 1.55;
}

.risk-pill {
  height: 26px;
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  padding: 0 9px;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 900;
}

.risk-pill.high {
  color: #ffd4d4;
  background: rgba(255, 118, 118, 0.13);
}

.risk-pill.medium,
.risk-pill.unknown {
  color: #f6d787;
  background: rgba(246, 215, 135, 0.12);
}

.risk-pill.low {
  color: #baf5ff;
  background: rgba(128, 215, 232, 0.10);
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 12px;
}

.meta span {
  max-width: 100%;
  padding: 5px 8px;
  border-radius: 8px;
  color: rgba(177, 194, 206, 0.5);
  background: rgba(137, 169, 191, 0.05);
  font-size: 0.72rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.delete-button {
  margin-top: 12px;
  height: 32px;
  border: 1px solid rgba(255, 118, 118, 0.24);
  border-radius: 8px;
  color: #ffd4d4;
  background: rgba(255, 118, 118, 0.08);
  padding: 0 10px;
  cursor: pointer;
}

@media (max-width: $mobile) {
  .filters {
    grid-template-columns: 1fr;
  }
}
</style>
