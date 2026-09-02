import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import CryptoJS from 'crypto-js'
import { useDatabase } from '@/composables/useDatabase'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const isAuthenticated = computed(() => !!user.value)

  const { getUserByUsername, createUser } = useDatabase()

  const login = async (username, password) => {
    try {
      const userData = await getUserByUsername(username)
      if (!userData) {
        throw new Error('用户不存在')
      }

      const hashedPassword = CryptoJS.SHA256(password).toString()
      if (userData.password !== hashedPassword) {
        throw new Error('密码错误')
      }

      user.value = {
        username: userData.username,
        avatar: userData.avatar
      }

      return { success: true }
    } catch (error) {
      return { success: false, message: error.message }
    }
  }

  const guestLogin = () => {
    user.value = {
      username: '游客用户',
      avatar: '/default-avatar.svg',
      isGuest: true
    }

    return { success: true }
  }

  const register = async (username, password, avatar = null) => {
    try {
      const hashedPassword = CryptoJS.SHA256(password).toString()
      const userData = {
        username,
        password: hashedPassword,
        avatar: avatar || '/default-avatar.svg'
      }

      await createUser(userData)
      user.value = {
        username: userData.username,
        avatar: userData.avatar
      }

      return { success: true }
    } catch (error) {
      return { success: false, message: error.message }
    }
  }

  const logout = () => {
    user.value = null
  }

  return {
    user,
    isAuthenticated,
    login,
    guestLogin,
    register,
    logout
  }
})
