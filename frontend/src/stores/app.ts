import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const collapsed = ref(false)
  const loading = ref(false)

  function toggleCollapsed() {
    collapsed.value = !collapsed.value
  }

  function setLoading(val: boolean) {
    loading.value = val
  }

  return { collapsed, loading, toggleCollapsed, setLoading }
})
