<template>
  <a-layout class="main-layout">
    <a-layout-sider
      v-model:collapsed="collapsed"
      :trigger="null"
      collapsible
      :width="240"
      :collapsed-width="80"
      class="layout-sider"
    >
      <div class="logo">
        <img v-if="!collapsed" src="@/assets/images/logo-ai4ss.png" alt="AI4SS" class="logo-icon" />
        <span v-if="!collapsed" class="logo-text">AI素养评测</span>
        <span v-else class="logo-text-collapsed">AI</span>
      </div>
      <a-menu
        v-model:selectedKeys="selectedKeys"
        theme="dark"
        mode="inline"
        @click="onMenuClick"
      >
        <a-menu-item v-for="item in visibleMenuItems" :key="item.key">
          <component :is="item.icon" />
          <span>{{ item.label }}</span>
        </a-menu-item>
      </a-menu>

      <!-- Sidebar footer with logos & copyright -->
      <div class="sider-footer">
        <div class="sider-footer-logos">
          <img src="@/assets/images/logo-yunhan.png" alt="云瀚" class="footer-logo" />
          <img src="@/assets/images/logo-ai4ss.png" alt="AI4SS" class="footer-logo" />
        </div>
        <div v-if="!collapsed" class="sider-footer-text">
          云瀚社区 & AI4SS实验室
        </div>
      </div>
    </a-layout-sider>

    <a-layout>
      <a-layout-header class="layout-header">
        <div class="header-left">
          <MenuUnfoldOutlined
            v-if="collapsed"
            class="trigger"
            @click="collapsed = false"
          />
          <MenuFoldOutlined
            v-else
            class="trigger"
            @click="collapsed = true"
          />
          <a-breadcrumb class="header-breadcrumb">
            <a-breadcrumb-item>
              <HomeOutlined />
            </a-breadcrumb-item>
            <a-breadcrumb-item>{{ currentPageLabel }}</a-breadcrumb-item>
          </a-breadcrumb>
        </div>
        <div class="header-right">
          <a-tag v-if="userStore.roleName" color="blue" style="margin-right: 12px">{{ userStore.roleName }}</a-tag>
          <a-dropdown>
            <span class="user-info">
              <a-avatar size="small" :style="{ backgroundColor: '#1F4E79' }">
                {{ (userStore.userInfo?.full_name || userStore.userInfo?.username || 'U').charAt(0).toUpperCase() }}
              </a-avatar>
              <span class="username">{{ userStore.userInfo?.full_name || userStore.userInfo?.username || '用户' }}</span>
            </span>
            <template #overlay>
              <a-menu>
                <a-menu-item @click="handleLogout">
                  <LogoutOutlined />
                  退出登录
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </a-layout-header>

      <a-layout-content class="layout-content">
        <router-view />
      </a-layout-content>

      <a-layout-footer class="layout-footer">
        <div class="footer-content">
          <div class="footer-logos">
            <img src="@/assets/images/logo-yunhan.png" alt="云瀚社区" class="footer-inline-logo" />
            <img src="@/assets/images/logo-ai4ss.png" alt="AI4SS Lab" class="footer-inline-logo" />
          </div>
          <div class="footer-text">
            AI素养评测平台 &copy; 2026 &nbsp;&middot;&nbsp; 云瀚社区与AI4SS实验室版权所有
          </div>
        </div>
      </a-layout-footer>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
import { ref, computed, watch, type Component } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import {
  HomeOutlined,
  DashboardOutlined,
  FolderOutlined,
  FileTextOutlined,
  SnippetsOutlined,
  FormOutlined,
  BarChartOutlined,
  TeamOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  UserOutlined,
  LogoutOutlined,
} from '@ant-design/icons-vue'

interface MenuItem {
  key: string
  label: string
  icon: Component
  roles: string[]
}

const allMenuItems: MenuItem[] = [
  { key: 'Home', label: '首页', icon: HomeOutlined, roles: ['admin', 'organizer', 'reviewer'] },
  { key: 'Dashboard', label: '工作台', icon: DashboardOutlined, roles: ['admin', 'organizer', 'reviewer'] },
  { key: 'Materials', label: '素材管理', icon: FolderOutlined, roles: ['admin'] },
  { key: 'Questions', label: '题库管理', icon: FileTextOutlined, roles: ['admin', 'organizer', 'reviewer'] },
  { key: 'Papers', label: '试卷管理', icon: SnippetsOutlined, roles: ['admin', 'organizer'] },
  { key: 'Exams', label: '可用试卷', icon: FormOutlined, roles: ['admin', 'organizer', 'reviewer', 'examinee'] },
  { key: 'Scores', label: '成绩管理', icon: BarChartOutlined, roles: ['admin', 'organizer', 'reviewer', 'examinee'] },
  { key: 'Users', label: '用户管理', icon: TeamOutlined, roles: ['admin'] },
  { key: 'SystemConfig', label: '系统管理', icon: SettingOutlined, roles: ['admin'] },
]

const menuLabelMap: Record<string, string> = {}
allMenuItems.forEach(item => { menuLabelMap[item.key] = item.label })

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const collapsed = ref(false)
const selectedKeys = ref<string[]>([route.name as string || 'Home'])

const visibleMenuItems = computed(() => {
  const role = userStore.userInfo?.role || ''
  return allMenuItems.filter(item => item.roles.includes(role))
})

const currentPageLabel = computed(() => {
  const name = route.name as string
  return menuLabelMap[name] || name || ''
})

watch(() => route.name, (name) => {
  selectedKeys.value = [name as string]
})

function onMenuClick({ key }: { key: string }) {
  router.push({ name: key })
}

function handleLogout() {
  userStore.logout()
  router.push({ name: 'Login' })
}
</script>

<style scoped>
.main-layout {
  min-height: 100vh;
}

.layout-sider {
  background: var(--primary-color) !important;
  display: flex;
  flex-direction: column;
}

.layout-sider :deep(.ant-layout-sider-children) {
  background: var(--primary-color);
  display: flex;
  flex-direction: column;
}

.layout-sider :deep(.ant-menu) {
  background: var(--primary-color);
  flex: 1;
}

.layout-sider :deep(.ant-menu-item) {
  margin: 2px 8px;
  border-radius: 6px;
}

.layout-sider :deep(.ant-menu-item-selected) {
  background-color: var(--primary-active) !important;
}

.logo {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #fff;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
  padding: 0 16px;
}

.logo-icon {
  width: 32px;
  height: 32px;
  border-radius: 6px;
}

.logo-text {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 1px;
  white-space: nowrap;
}

.logo-text-collapsed {
  font-size: 20px;
  font-weight: 800;
  color: #fff;
}

/* Sidebar footer */
.sider-footer {
  padding: 12px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  text-align: center;
}

.sider-footer-logos {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 6px;
}

.sider-footer-logos .footer-logo {
  width: 28px;
  height: 28px;
  opacity: 0.85;
  transition: opacity 0.3s;
}

.sider-footer-logos .footer-logo:hover {
  opacity: 1;
}

.sider-footer-text {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.45);
  white-space: nowrap;
  line-height: 1.4;
}

/* Header */
.layout-header {
  background: #fff;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  z-index: 1;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-breadcrumb {
  font-size: 14px;
}

.trigger {
  font-size: 18px;
  cursor: pointer;
  transition: color 0.3s;
  color: var(--text-color);
}

.trigger:hover {
  color: var(--primary-color);
}

.header-right {
  display: flex;
  align-items: center;
}

.user-info {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-color);
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.2s;
}

.user-info:hover {
  background: var(--primary-bg);
}

.username {
  font-size: 14px;
  font-weight: 500;
}

/* Content */
.layout-content {
  margin: 24px;
  min-height: 280px;
}

/* Footer */
.layout-footer {
  text-align: center;
  padding: 16px 24px;
  background: transparent;
}

.footer-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.footer-logos {
  display: flex;
  align-items: center;
  gap: 12px;
}

.footer-inline-logo {
  height: 28px;
  opacity: 0.5;
  transition: opacity 0.3s;
}

.footer-inline-logo:hover {
  opacity: 0.85;
}

.footer-text {
  color: var(--text-hint);
  font-size: 12px;
}
</style>
