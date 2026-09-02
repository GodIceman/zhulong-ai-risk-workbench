import localforage from 'localforage'

// 配置localForage
const userStore = localforage.createInstance({
  name: 'ZhulongUsers',
  storeName: 'users'
})

const historyStore = localforage.createInstance({
  name: 'ZhulongHistory',
  storeName: 'history'
})

export const useDatabase = () => {
  // 用户相关操作
  const getUserByUsername = async (username) => {
    return await userStore.getItem(username)
  }

  const createUser = async (userData) => {
    const existingUser = await userStore.getItem(userData.username)
    if (existingUser) {
      throw new Error('用户名已存在')
    }

    await userStore.setItem(userData.username, userData)
  }

  const updateUser = async (username, updates) => {
    const user = await userStore.getItem(username)
    if (!user) {
      throw new Error('用户不存在')
    }

    const updatedUser = { ...user, ...updates }
    await userStore.setItem(username, updatedUser)
    return updatedUser
  }

  // 历史记录相关操作
  const getHistory = async (limit = 100) => {
    const keys = await historyStore.keys()
    const records = await Promise.all(
      keys.map(key => historyStore.getItem(key))
    )
    return records
      .filter(record => record)
      .sort((a, b) => new Date(b.time) - new Date(a.time))
      .slice(0, limit)
  }

  const addHistoryRecord = async (record) => {
    const id = `record_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    const newRecord = {
      id,
      time: new Date().toISOString(),
      ...record
    }

    await historyStore.setItem(id, newRecord)
    return newRecord
  }

  const updateHistoryRecord = async (id, updates) => {
    const record = await historyStore.getItem(id)
    if (!record) {
      throw new Error('记录不存在')
    }

    const updatedRecord = { ...record, ...updates }
    await historyStore.setItem(id, updatedRecord)
    return updatedRecord
  }

  const deleteHistoryRecord = async (id) => {
    await historyStore.removeItem(id)
  }

  return {
    getUserByUsername,
    createUser,
    updateUser,
    getHistory,
    addHistoryRecord,
    updateHistoryRecord,
    deleteHistoryRecord
  }
}
