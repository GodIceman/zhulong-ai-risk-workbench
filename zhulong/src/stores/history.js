import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useDatabase } from '@/composables/useDatabase'

export const useHistoryStore = defineStore('history', () => {
  const history = ref([])
  const loading = ref(false)

  const {
    getHistory,
    addHistoryRecord,
    updateHistoryRecord,
    deleteHistoryRecord
  } = useDatabase()

  const addRecord = async (record) => {
    const newRecord = await addHistoryRecord(record)
    history.value.unshift(newRecord)
    return newRecord
  }

  const loadHistory = async () => {
    loading.value = true
    try {
      const records = await getHistory()
      history.value = (records || []).filter((record) => ['image', 'article'].includes(record.type))
    } catch (error) {
      console.error('加载历史记录失败:', error)
    } finally {
      loading.value = false
    }
  }

  const updateRecord = async (id, updates) => {
    const updatedRecord = await updateHistoryRecord(id, updates)
    const index = history.value.findIndex((record) => record.id === id)
    if (index !== -1) {
      history.value[index] = updatedRecord
    }
    return updatedRecord
  }

  const deleteRecord = async (id) => {
    await deleteHistoryRecord(id)
    const index = history.value.findIndex((record) => record.id === id)
    if (index !== -1) {
      history.value.splice(index, 1)
    }
  }

  return {
    history,
    loading,
    loadHistory,
    addRecord,
    updateRecord,
    deleteRecord
  }
})
