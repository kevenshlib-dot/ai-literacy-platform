import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface UserInfo {
  id: string
  username: string
  email: string
  full_name: string | null
  role: string
  is_active: boolean
}

export const useUserStore = defineStore('user', () => {
  const token = ref<string>(localStorage.getItem('token') || '')

  const savedUserInfo = localStorage.getItem('userInfo')
  const userInfo = ref<UserInfo | null>(savedUserInfo ? JSON.parse(savedUserInfo) : null)

  const isLoggedIn = computed(() => !!token.value)

  const roleName = computed(() => {
    const roleMap: Record<string, string> = {
      admin: '管理员',
      organizer: '组织者',
      examinee: '被测者',
      reviewer: '审题员',
    }
    return roleMap[userInfo.value?.role || ''] || '未知'
  })

  function setToken(newToken: string) {
    token.value = newToken
    localStorage.setItem('token', newToken)
  }

  function setUserInfo(info: UserInfo) {
    userInfo.value = info
    localStorage.setItem('userInfo', JSON.stringify(info))
  }

  function logout() {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
  }

  return { token, userInfo, isLoggedIn, roleName, setToken, setUserInfo, logout }
})
