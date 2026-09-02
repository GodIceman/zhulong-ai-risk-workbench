<template>
  <section class="task-status" aria-live="polite" aria-busy="true">
    <header>
      <span>ANALYZING</span>
      <h2>正在分析{{ subjectLabel }}</h2>
      <p>{{ status?.detail || '正在创建检测任务' }}</p>
    </header>

    <div class="progress-block">
      <div class="progress-label">
        <span>{{ activeStage.label }}</span>
        <strong>{{ progress }}%</strong>
      </div>
      <div class="progress-track">
        <span :style="{ width: `${progress}%` }"></span>
      </div>
    </div>

    <ol class="stage-list">
      <li
        v-for="(stage, index) in stages"
        :key="stage.key"
        :class="{ active: activeStageIndex === index, completed: activeStageIndex > index }"
      >
        <span class="stage-index">{{ index + 1 }}</span>
        <div>
          <strong>{{ stage.label }}</strong>
          <p>{{ stage.description }}</p>
        </div>
      </li>
    </ol>

    <p v-if="taskId" class="task-id">任务编号 {{ taskId }}</p>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  taskId: {
    type: String,
    default: ''
  },
  status: {
    type: Object,
    default: null
  },
  mediaType: {
    type: String,
    default: 'image'
  }
})

const subjectLabel = computed(() => ({
  image: '图片',
  video: '视频',
  article: '文章'
}[props.mediaType] || '内容'))

const stages = [
  { key: 'validate', label: '安全校验', description: '检查格式、大小与分辨率' },
  { key: 'source', label: '读取来源', description: '解析 EXIF、XMP 与内容凭证' },
  { key: 'model', label: '模型分析', description: '运行本地检测模型' },
  { key: 'report', label: '汇总结论', description: '融合证据并生成报告' }
]

const stageByStatus = {
  received: 0,
  validating: 0,
  routing: 1,
  extracting: 1,
  detecting: 2,
  aggregating: 3,
  completed: 3,
  uncertain: 3,
  failed: 3
}

const activeStageIndex = computed(() => stageByStatus[props.status?.key] ?? 0)
const activeStage = computed(() => stages[activeStageIndex.value])
const progress = computed(() => Math.max(0, Math.min(100, Number(props.status?.progress || 0))))
</script>

<style lang="scss" scoped>
.task-status {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  color: #e2eaf0;
}

header > span {
  color: #6fa8c7;
  font-size: 0.72rem;
  font-weight: 900;
  letter-spacing: 0.12em;
}

h2 {
  margin: 5px 0 3px;
  font-size: 1.18rem;
  letter-spacing: 0;
}

header p {
  min-height: 46px;
  color: rgba(181, 199, 213, 0.57);
  font-size: 0.86rem;
  line-height: 1.6;
}

.progress-block {
  margin-top: 26px;
}

.progress-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: rgba(199, 213, 223, 0.72);
  font-size: 0.84rem;
}

.progress-label strong {
  color: #82b2ca;
}

.progress-track {
  height: 7px;
  margin-top: 9px;
  border-radius: 4px;
  background: rgba(126, 158, 181, 0.11);
  overflow: hidden;
}

.progress-track span {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #4f86aa, #6aa8c7);
  box-shadow: 0 0 14px rgba(75, 135, 168, 0.2);
  transition: width 180ms ease;
}

.stage-list {
  display: grid;
  gap: 0;
  margin: 28px 0 0;
  padding: 0;
  list-style: none;
}

.stage-list li {
  min-height: 74px;
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 12px;
  position: relative;
  color: rgba(160, 181, 198, 0.41);
}

.stage-list li::after {
  content: '';
  width: 1px;
  position: absolute;
  top: 30px;
  bottom: 0;
  left: 14px;
  background: rgba(120, 158, 185, 0.12);
}

.stage-list li:last-child::after {
  display: none;
}

.stage-index {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  position: relative;
  z-index: 1;
  border: 1px solid rgba(120, 158, 185, 0.15);
  border-radius: 50%;
  background: rgba(7, 23, 38, 0.78);
  font-size: 0.74rem;
  font-weight: 900;
}

.stage-list strong {
  display: block;
  padding-top: 2px;
  font-size: 0.86rem;
}

.stage-list p {
  margin-top: 3px;
  font-size: 0.76rem;
}

.stage-list li.active {
  color: #b9d3e2;
}

.stage-list li.active .stage-index {
  border-color: rgba(99, 161, 199, 0.5);
  color: #e1eaf0;
  background: rgba(43, 88, 119, 0.3);
  box-shadow: 0 0 16px rgba(57, 112, 145, 0.14);
}

.stage-list li.completed {
  color: #8be3dc;
}

.stage-list li.completed .stage-index {
  border-color: rgba(80, 211, 196, 0.38);
  background: rgba(26, 127, 119, 0.22);
}

.task-id {
  max-width: 100%;
  margin-top: auto;
  color: rgba(157, 179, 195, 0.44);
  font-size: 0.72rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
