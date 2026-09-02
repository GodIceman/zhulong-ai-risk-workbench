import localforage from 'localforage'
import LRUCache from 'lru-cache'

const userStore = localforage.createInstance({
  name: 'ZhulongUsers',
  storeName: 'users'
})

const historyStore = localforage.createInstance({
  name: 'ZhulongHistory',
  storeName: 'history'
})

const metaStore = localforage.createInstance({
  name: 'ZhulongMeta',
  storeName: 'meta'
})

const userCache = new LRUCache({
  max: 100,
  ttl: 1000 * 60 * 30,
  updateAgeOnGet: true
})

const historyCache = new LRUCache({
  max: 500,
  ttl: 1000 * 60 * 10,
  updateAgeOnGet: true
})

export const useDatabase = () => {
  const getUserByUsername = async (username) => {
    const cacheKey = `user_${username}`
    let user = userCache.get(cacheKey)

    if (!user) {
      user = await userStore.getItem(username)
      if (user) {
        userCache.set(cacheKey, user)
      }
    }

    return user
  }

  const createUser = async (userData) => {
    const existingUser = await userStore.getItem(userData.username)
    if (existingUser) {
      throw new Error('用户名已存在')
    }

    await userStore.setItem(userData.username, userData)
    userCache.set(`user_${userData.username}`, userData)
  }

  const updateUser = async (username, updates) => {
    const user = await userStore.getItem(username)
    if (!user) {
      throw new Error('用户不存在')
    }

    const updatedUser = { ...user, ...updates }
    await userStore.setItem(username, updatedUser)
    userCache.set(`user_${username}`, updatedUser)
    return updatedUser
  }

  const getHistory = async (limit = 100) => {
    const cacheKey = 'history_list'
    let history = historyCache.get(cacheKey)

    if (!history) {
      const keys = await historyStore.keys()
      const records = await Promise.all(
        keys.map((key) => historyStore.getItem(key))
      )

      history = records
        .filter((record) => record)
        .sort((a, b) => new Date(b.time) - new Date(a.time))
        .slice(0, limit)

      historyCache.set(cacheKey, history)
    }

    return history
  }

  const addHistoryRecord = async (record) => {
    const id = `record_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`
    const newRecord = {
      id,
      time: new Date().toISOString(),
      ...record
    }

    await historyStore.setItem(id, newRecord)
    historyCache.delete('history_list')

    return newRecord
  }

  const updateHistoryRecord = async (id, updates) => {
    const record = await historyStore.getItem(id)
    if (!record) {
      throw new Error('记录不存在')
    }

    const updatedRecord = { ...record, ...updates }
    await historyStore.setItem(id, updatedRecord)
    historyCache.delete('history_list')

    return updatedRecord
  }

  const deleteHistoryRecord = async (id) => {
    await historyStore.removeItem(id)
    historyCache.delete('history_list')
  }

  const clearHistoryAll = async () => {
    const keys = await historyStore.keys()
    for (const key of keys) {
      await historyStore.removeItem(key)
    }

    historyCache.delete('history_list')
    await metaStore.setItem('history_seeded', true)
  }

  const getMeta = async (key) => {
    return await metaStore.getItem(key)
  }

  const setMeta = async (key, value) => {
    await metaStore.setItem(key, value)
  }

  return {
    getUserByUsername,
    createUser,
    updateUser,
    getHistory,
    addHistoryRecord,
    updateHistoryRecord,
    deleteHistoryRecord,
    clearHistoryAll,
    getMeta,
    setMeta
  }
}
