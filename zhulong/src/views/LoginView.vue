<template>
  <div class="login-container">
    <AnimatedShaderBackground />
    <div class="center-aurora"></div>
    <div class="ambient-glow ambient-glow-primary"></div>
    <div class="ambient-glow ambient-glow-warm"></div>
    <div class="grain-layer"></div>

    <main class="login-shell">
      <section class="brand-panel" aria-label="烛龙系统介绍">
        <div class="brand-mark">
          <span class="brand-name">烛龙</span>
        </div>
        <h1>让每一份内容都有迹可查</h1>
        <p v-if="isDemoMode" class="demo-note">静态产品演示：请使用游客登录，文件不会上传，报告为固定虚构数据。</p>
      </section>

      <section class="login-card" aria-label="登录">
        <form @submit.prevent="handleLogin" class="login-form">
          <label class="input-group">
            <span>用户名</span>
            <input
              v-model="form.username"
              type="text"
              placeholder="请输入用户名"
              required
              class="form-input"
              autocomplete="username"
            />
          </label>

          <label class="input-group">
            <span>密码</span>
            <div class="input-shell">
              <input
                v-model="form.password"
                :type="showPassword ? 'text' : 'password'"
                placeholder="请输入密码"
                required
                class="form-input with-right-icon"
                autocomplete="current-password"
              />
              <button
                type="button"
                class="password-toggle"
                :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                @click="togglePasswordVisibility"
              >
                <EyeOff v-if="showPassword" :size="17" :stroke-width="1.8" aria-hidden="true" />
                <Eye v-else :size="17" :stroke-width="1.8" aria-hidden="true" />
              </button>
            </div>
          </label>

          <button
            type="submit"
            class="login-btn"
            :disabled="loading"
          >
            <span v-if="!loading">登录系统</span>
            <span v-else class="loading-spinner"></span>
          </button>

          <button
            type="button"
            class="guest-btn"
            :disabled="loading"
            @click="handleGuestLogin"
          >
            游客登录
          </button>

          <div class="form-footer">
            <span>还没有账号？</span>
            <button type="button" @click="showRegister = true" class="link-btn">
              注册新账号
            </button>
          </div>
        </form>
      </section>
    </main>

    <div v-if="showRegister" class="modal-overlay" @click="showRegister = false">
      <div class="modal-content" @click.stop>
        <button @click="showRegister = false" class="close-btn" aria-label="关闭注册窗口">×</button>
        <div class="modal-header">
          <p class="eyebrow">CREATE ACCOUNT</p>
          <h2 class="modal-title">注册新账号</h2>
        </div>

        <form @submit.prevent="handleRegister" class="register-form">
          <label class="input-group">
            <span>用户名</span>
            <input
              v-model="registerForm.username"
              type="text"
              placeholder="设置用户名"
              required
              class="form-input"
              autocomplete="username"
            />
          </label>

          <label class="input-group">
            <span>密码</span>
            <input
              v-model="registerForm.password"
              type="password"
              placeholder="设置密码"
              required
              class="form-input"
              autocomplete="new-password"
            />
          </label>

          <label class="input-group">
            <span>确认密码</span>
            <input
              v-model="registerForm.confirmPassword"
              type="password"
              placeholder="再次输入密码"
              required
              class="form-input"
              autocomplete="new-password"
            />
          </label>

          <button type="submit" class="register-btn" :disabled="loading">
            <span v-if="!loading">完成注册</span>
            <span v-else class="loading-spinner"></span>
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Eye, EyeOff } from '@lucide/vue'
import AnimatedShaderBackground from '@/components/AnimatedShaderBackground.vue'
import { navigateWithTransition } from '@/composables/useRouteTransition'
import { useAuthStore } from '@/stores/auth'
import { isDemoMode } from '@/services/demoMode'

const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const showRegister = ref(false)
const showPassword = ref(false)

const form = reactive({
  username: '',
  password: ''
})

const registerForm = reactive({
  username: '',
  password: '',
  confirmPassword: ''
})

const togglePasswordVisibility = () => {
  showPassword.value = !showPassword.value
}

const handleLogin = async () => {
  loading.value = true
  try {
    const result = await authStore.login(form.username, form.password)
    if (result.success) {
      await navigateWithTransition(router, '/dashboard')
    } else {
      alert(result.message)
    }
  } catch (error) {
    alert('登录失败，请重试')
  } finally {
    loading.value = false
  }
}

const handleGuestLogin = async () => {
  authStore.guestLogin()
  await navigateWithTransition(router, '/dashboard')
}

const handleRegister = async () => {
  if (registerForm.password !== registerForm.confirmPassword) {
    alert('两次输入的密码不一致')
    return
  }

  loading.value = true
  try {
    const result = await authStore.register(
      registerForm.username,
      registerForm.password
    )
    if (result.success) {
      showRegister.value = false
      alert('注册成功，请登录')
    } else {
      alert(result.message)
    }
  } catch (error) {
    alert('注册失败，请重试')
  } finally {
    loading.value = false
  }
}

</script>

<style lang="scss" scoped>
.login-container {
  min-height: 100vh;
  background: #020511;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  color: #f7f4ec;
}

.center-aurora,
.ambient-glow,
.grain-layer {
  position: absolute;
  pointer-events: none;
}

.center-aurora {
  width: 62vw;
  height: 64vh;
  left: 58%;
  top: 50%;
  z-index: 1;
  transform: translate(-50%, -50%);
  background:
    radial-gradient(circle at 50% 47%, rgba(62, 197, 216, 0.22), transparent 38%),
    radial-gradient(circle at 50% 53%, rgba(239, 164, 72, 0.13), transparent 45%);
  filter: blur(22px);
  mix-blend-mode: screen;
}

.ambient-glow {
  z-index: 1;
  border-radius: 999px;
  filter: blur(18px);
  opacity: 0.78;
}

.ambient-glow-primary {
  width: 38vw;
  height: 38vw;
  left: 58%;
  bottom: -19vw;
  transform: translateX(-52%);
  background: radial-gradient(circle, rgba(33, 164, 191, 0.34), transparent 68%);
}

.ambient-glow-warm {
  width: 32vw;
  height: 32vw;
  right: 25vw;
  top: -17vw;
  background: radial-gradient(circle, rgba(218, 91, 43, 0.30), transparent 66%);
}

.grain-layer {
  inset: 0;
  z-index: 1;
  opacity: 0.14;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.025) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(circle at center, black, transparent 82%);
}

.login-shell {
  width: min(720px, calc(100% - 64px));
  min-height: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 26px;
  position: relative;
  z-index: 2;
  text-align: center;
}

.brand-panel {
  max-width: 720px;
  padding-left: 0;
}

.brand-mark {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 18px;
}

.brand-name {
  display: inline-block;
  font-size: clamp(3rem, 5vw, 4.9rem);
  line-height: 1;
  font-weight: 900;
  letter-spacing: 0.08em;
  color: transparent;
  background: linear-gradient(180deg, #fff4c9 0%, #f7d77e 48%, #dfa94e 100%);
  background-clip: text;
  -webkit-background-clip: text;
  filter:
    drop-shadow(0 0 15px rgba(235, 174, 75, 0.34))
    drop-shadow(0 9px 22px rgba(0, 0, 0, 0.42));
  view-transition-name: zhulong-wordmark;
}

.brand-kicker,
.eyebrow {
  color: #80d7e8;
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.brand-panel h1 {
  max-width: none;
  margin: 0 0 16px;
  font-size: clamp(2.25rem, 3.35vw, 3.65rem);
  line-height: 1.1;
  color: transparent;
  background: linear-gradient(105deg, #fffef8 8%, #edf8ff 55%, #fff0ca 100%);
  background-clip: text;
  -webkit-background-clip: text;
  font-weight: 820;
  letter-spacing: 0.01em;
  white-space: nowrap;
  filter: drop-shadow(0 10px 28px rgba(0, 0, 0, 0.4));
}

.demo-note {
  max-width: 620px;
  margin: 0 auto;
  color: rgba(155, 234, 214, 0.78);
  font-size: 0.82rem;
  line-height: 1.6;
}

.login-card,
.modal-content {
  border: 1px solid rgba(214, 237, 243, 0.16);
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.065), rgba(255, 255, 255, 0.012)),
    rgba(5, 17, 31, 0.58);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.13),
    inset 0 -1px 0 rgba(128, 209, 223, 0.035),
    0 30px 90px rgba(0, 0, 0, 0.46);
  backdrop-filter: blur(30px) saturate(145%);
}

.login-card {
  width: 100%;
  padding: 30px;
  border-radius: 20px;
  position: relative;
  overflow: hidden;
  max-width: 420px;
}

.login-card::before,
.modal-content::before {
  content: '';
  position: absolute;
  inset: 0 11% auto;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.34), transparent);
  pointer-events: none;
}

.login-card::after,
.modal-content::after {
  content: '';
  position: absolute;
  width: 230px;
  height: 150px;
  top: -100px;
  right: -70px;
  border-radius: 50%;
  background: rgba(239, 180, 86, 0.08);
  filter: blur(45px);
  pointer-events: none;
}

.login-form,
.register-form {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  text-align: left;
}

.input-group > span {
  color: rgba(255, 248, 226, 0.88);
  font-size: 0.84rem;
  font-weight: 760;
  letter-spacing: 0.04em;
}

.input-shell {
  position: relative;
  display: flex;
  align-items: center;
}

.form-input {
  width: 100%;
  height: 46px;
  padding: 0 15px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.025), transparent),
    rgba(1, 10, 23, 0.43);
  border: 1px solid rgba(175, 224, 234, 0.15);
  border-radius: 12px;
  color: #fff8e9;
  font-size: 0.96rem;
  font-weight: 540;
  letter-spacing: 0.012em;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
  transition: border-color $transition-normal, box-shadow $transition-normal, background $transition-normal;
}

.form-input.with-right-icon {
  padding-right: 48px;
}

.form-input::placeholder {
  color: rgba(221, 232, 235, 0.48);
  font-weight: 450;
}

.form-input:focus {
  outline: none;
}

.password-toggle {
  position: absolute;
  right: 9px;
  width: 32px;
  height: 32px;
  display: inline-grid;
  place-items: center;
  border: 0;
  color: rgba(181, 205, 221, 0.56);
  background: transparent;
  cursor: pointer;
  transition: color $transition-fast;
}

.password-toggle:hover {
  color: rgba(218, 237, 249, 0.9);
}

.password-toggle:focus-visible {
  outline: none;
  color: rgba(218, 237, 249, 0.94);
}

.password-toggle svg {
  display: block;
}

.login-btn,
.register-btn,
.guest-btn {
  height: 48px;
  border-radius: 12px;
  cursor: pointer;
  font-size: 1rem;
  font-weight: 800;
  letter-spacing: 0.025em;
  transform: translateZ(0);
  backface-visibility: hidden;
  -webkit-font-smoothing: antialiased;
  transition: color 160ms ease, background-color 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
}

.register-btn {
  border: 0;
  margin-top: 6px;
  color: #eaffff;
  background: linear-gradient(135deg, #164d64 0%, #0e314d 52%, #0a2038 100%);
  box-shadow: 0 16px 30px rgba(4, 20, 36, 0.34), 0 0 20px rgba(45, 171, 196, 0.12);
}

.login-btn {
  border: 1px solid rgba(126, 196, 238, 0.22);
  margin-top: 6px;
  color: #f4fbff;
  background: linear-gradient(135deg, #438fc6 0%, #3379b1 52%, #295f92 100%);
  box-shadow:
    0 10px 24px rgba(15, 65, 104, 0.3),
    inset 0 1px 0 rgba(207, 238, 255, 0.18);
}

.guest-btn {
  border: 1px solid rgba(177, 225, 235, 0.18);
  color: #dffaff;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.008)),
    rgba(2, 13, 29, 0.44);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.085);
}

.register-btn:hover {
  box-shadow: 0 20px 38px rgba(4, 20, 36, 0.40), 0 0 26px rgba(64, 201, 221, 0.16);
}

.login-btn:hover {
  border-color: rgba(151, 211, 246, 0.34);
  box-shadow:
    0 10px 24px rgba(15, 65, 104, 0.3),
    inset 0 1px 0 rgba(218, 243, 255, 0.24);
}

.guest-btn:hover {
  border-color: rgba(177, 225, 235, 0.28);
  color: #effdff;
  background-color: rgba(23, 48, 63, 0.62);
}

.login-btn:active,
.register-btn:active,
.guest-btn:active {
  transform: translateZ(0);
}

.login-btn:focus-visible,
.register-btn:focus-visible,
.guest-btn:focus-visible {
  outline: none;
  border-color: rgba(255, 255, 255, 0.34);
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.14), 0 0 26px rgba(255, 255, 255, 0.10);
}

.login-btn:disabled,
.register-btn:disabled,
.guest-btn:disabled {
  opacity: 0.66;
  cursor: not-allowed;
  transform: none;
}

.form-footer {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  color: rgba(235, 239, 237, 0.68);
  font-size: 0.87rem;
  letter-spacing: 0.012em;
}

.link-btn {
  padding: 0;
  background: none;
  border: none;
  color: #62a9d8;
  cursor: pointer;
  font-size: 0.87rem;
  font-weight: 760;
  letter-spacing: 0.012em;
  transition: color $transition-fast;
}

.link-btn:hover {
  color: #8bc9ed;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(1, 5, 15, 0.72);
  backdrop-filter: blur(12px);
}

.modal-content {
  width: min(420px, 100%);
  position: relative;
  padding: 30px;
  border-radius: 20px;
  overflow: hidden;
}

.modal-header {
  position: relative;
  z-index: 1;
  margin-bottom: 26px;
  text-align: left;
}

.modal-title {
  margin: 5px 0 0;
  color: #fff8e9;
  font-size: 1.58rem;
  line-height: 1.2;
  font-weight: 800;
}

.close-btn {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 32px;
  height: 32px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(247, 244, 236, 0.82);
  cursor: pointer;
  font-size: 1.3rem;
  line-height: 1;
  transition: background $transition-fast, color $transition-fast;
}

.close-btn:hover {
  background: rgba(243, 210, 118, 0.14);
  color: #f3d276;
}

.loading-spinner {
  display: inline-block;
  width: 20px;
  height: 20px;
  border: 2px solid rgba(22, 8, 10, 0.28);
  border-radius: 50%;
  border-top-color: #16080a;
  animation: spin 0.85s ease-in-out infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
