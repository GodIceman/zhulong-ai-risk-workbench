<template>
  <div class="chat-composer" :class="{ focused: isFocused }">
    <div class="textarea-wrap">
      <textarea
        ref="textareaRef"
        v-model="message"
        rows="1"
        maxlength="100000"
        :placeholder="placeholder"
        aria-label="粘贴要检测的文字"
        @input="handleInput"
        @focus="isFocused = true"
        @blur="isFocused = false"
        @keydown="handleKeydown"
      ></textarea>
    </div>

    <div class="composer-footer">
      <div class="composer-tools">
        <button class="tool-button" type="button" aria-label="上传图片或视频并自动检测" @click="$emit('attach')">
          <Paperclip :size="18" aria-hidden="true" />
        </button>
      </div>

      <button
        class="send-button"
        type="button"
        :disabled="!message.trim()"
        aria-label="自动识别内容并开始检测"
        @click="$emit('submit')"
      >
        <Send :size="16" aria-hidden="true" />
        <span>{{ message.trim() ? '检测文字' : '开始检测' }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Paperclip, Send } from '@lucide/vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: '粘贴要检测的文字，或上传图片、视频…'
  }
})

const emit = defineEmits(['update:modelValue', 'attach', 'submit'])
const textareaRef = ref(null)
const isFocused = ref(false)

const message = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const adjustHeight = () => {
  const textarea = textareaRef.value
  if (!textarea) return
  textarea.style.height = '64px'
  textarea.style.height = `${Math.min(Math.max(textarea.scrollHeight, 64), 180)}px`
}

const handleInput = () => {
  adjustHeight()
}

const handleKeydown = (event) => {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  if (message.value.trim()) emit('submit')
}

watch(() => props.modelValue, () => nextTick(adjustHeight))

onMounted(() => {
  window.addEventListener('resize', adjustHeight)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', adjustHeight)
})
</script>

<style lang="scss" scoped>
.chat-composer {
  position: relative;
  width: 100%;
  border: 1px solid rgba(176, 215, 250, 0.16);
  border-radius: 18px;
  color: #f7f7fa;
  background:
    linear-gradient(145deg, rgba(206, 232, 255, 0.075), rgba(109, 177, 235, 0.018)),
    rgba(9, 23, 39, 0.58);
  box-shadow:
    inset 0 1px 0 rgba(224, 241, 255, 0.13),
    inset 0 -1px 0 rgba(124, 190, 244, 0.035),
    0 30px 90px rgba(1, 8, 18, 0.42);
  backdrop-filter: blur(30px) saturate(145%);
  transition: border-color 180ms ease, box-shadow 180ms ease, background 180ms ease;
}

.chat-composer::before {
  content: '';
  position: absolute;
  inset: 0 10% auto;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(198, 229, 255, 0.38), transparent);
  pointer-events: none;
}

.chat-composer.focused {
  border-color: rgba(96, 176, 247, 0.42);
  background:
    linear-gradient(145deg, rgba(210, 235, 255, 0.09), rgba(91, 165, 229, 0.025)),
    rgba(8, 24, 42, 0.64);
  box-shadow:
    inset 0 1px 0 rgba(224, 242, 255, 0.15),
    0 0 0 4px rgba(59, 130, 246, 0.08),
    0 34px 100px rgba(1, 9, 20, 0.48);
}

.textarea-wrap {
  padding: 15px 16px 7px;
}

textarea {
  width: 100%;
  min-height: 64px;
  max-height: 180px;
  display: block;
  padding: 6px 3px;
  border: 0;
  outline: 0;
  resize: none;
  overflow-y: auto;
  color: rgba(255, 255, 255, 0.92);
  background: transparent;
  font: inherit;
  font-size: 0.94rem;
  line-height: 1.65;
}

textarea::placeholder {
  color: rgba(211, 231, 248, 0.4);
}

.composer-footer,
.composer-tools,
.tool-button,
.send-button {
  display: flex;
  align-items: center;
}

.composer-footer {
  min-height: 62px;
  justify-content: space-between;
  gap: 14px;
  padding: 10px 13px;
  border-top: 1px solid rgba(176, 215, 250, 0.1);
}

.composer-tools {
  gap: 5px;
}

.tool-button {
  width: 38px;
  height: 38px;
  justify-content: center;
  border: 0;
  border-radius: 10px;
  color: rgba(205, 229, 248, 0.58);
  background: transparent;
  cursor: pointer;
  transition: color 150ms ease, background 150ms ease, transform 150ms ease;
}

.tool-button:hover {
  color: #edf8ff;
  background: rgba(91, 169, 235, 0.13);
}

.tool-button:active {
  transform: scale(0.94);
}

.send-button {
  min-height: 39px;
  justify-content: center;
  gap: 7px;
  padding: 0 14px;
  border: 1px solid rgba(121, 172, 201, 0.62);
  border-radius: 10px;
  color: #f1f6f8;
  background: linear-gradient(135deg, #5c96b6, #437b9d);
  box-shadow: 0 8px 24px rgba(32, 86, 119, 0.2);
  cursor: pointer;
  font: inherit;
  font-size: 0.78rem;
  font-weight: 800;
  transition: transform 150ms ease, background 150ms ease, color 150ms ease, border-color 150ms ease, box-shadow 150ms ease;
}

.send-button:hover:not(:disabled) {
  border-color: rgba(139, 187, 213, 0.72);
  background: linear-gradient(135deg, #6aa2c0, #5189a8);
  box-shadow: 0 10px 28px rgba(32, 86, 119, 0.26);
  transform: translateY(-1px);
}

.send-button:active:not(:disabled) {
  transform: scale(0.98);
}

.send-button:disabled {
  border-color: rgba(170, 211, 246, 0.08);
  color: rgba(207, 228, 245, 0.4);
  background: rgba(105, 174, 232, 0.08);
  box-shadow: none;
  cursor: not-allowed;
}

@media (max-width: $mobile) {
  .chat-composer {
    border-radius: 16px;
  }

  .textarea-wrap {
    padding: 13px 13px 5px;
  }

  textarea {
    font-size: 0.9rem;
  }

  .send-button {
    padding: 0 12px;
  }

}

@media (prefers-reduced-motion: reduce) {
  .chat-composer,
  .tool-button,
  .send-button {
    transition: none;
  }
}
</style>
