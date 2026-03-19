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
        <span v-if="!collapsed">AI素养评测</span>
        <span v-else>AI</span>
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
        </div>
        <div class="header-right">
          <a-tag v-if="userStore.roleName" style="margin-right: 12px">{{ userStore.roleName }}</a-tag>
          <a-dropdown>
            <span class="user-info">
              <UserOutlined />
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
        AI素养评测平台 &copy; 2026
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
  FormOutlined,
  EditOutlined,
  BarChartOutlined,
  TeamOutlined,
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
  { key: 'Exams', label: '考试管理', icon: FormOutlined, roles: ['admin', 'organizer'] },
  { key: 'TakeExam', label: '在线考试', icon: EditOutlined, roles: ['admin', 'organizer', 'reviewer', 'examinee'] },
  { key: 'Scores', label: '成绩管理', icon: BarChartOutlined, roles: ['admin', 'organizer', 'reviewer', 'examinee'] },
  { key: 'Users', label: '用户管理', icon: TeamOutlined, roles: ['admin'] },
]

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const collapsed = ref(false)
const selectedKeys = ref<string[]>([(route.name === 'ExamCompose' ? 'Exams' : route.name as string) || 'Home'])

const visibleMenuItems = computed(() => {
  const role = userStore.userInfo?.role || ''
  return allMenuItems.filter(item => item.roles.includes(role))
})

function resolveSelectedKey(name: string | undefined) {
  if (name === 'ExamCompose') return 'Exams'
  return name || 'Home'
}

watch(() => route.name, (name) => {
  selectedKeys.value = [resolveSelectedKey(name as string | undefined)]
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
}

.layout-sider :deep(.ant-layout-sider-children) {
  background: var(--primary-color);
}

.layout-sider :deep(.ant-menu) {
  background: var(--primary-color);
}

.layout-sider :deep(.ant-menu-item-selected) {
  background-color: var(--primary-active) !important;
}

.logo {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 18px;
  font-weight: 700;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.layout-header {
  background: #fff;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  z-index: 1;
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
}

.username {
  font-size: 14px;
}

.layout-content {
  margin: 24px;
  min-height: 280px;
}

.layout-footer {
  text-align: center;
  color: var(--text-hint);
  font-size: 12px;
}
</style>
