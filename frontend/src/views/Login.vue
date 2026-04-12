<template>
  <div class="login-page">
    <!-- Decorative background shapes -->
    <div class="bg-shape bg-shape-1"></div>
    <div class="bg-shape bg-shape-2"></div>
    <div class="bg-shape bg-shape-3"></div>

    <div class="login-container">
      <div class="login-header">
        <div class="login-logos">
          <img src="@/assets/images/logo-yunhan.png" alt="云瀚社区" class="header-logo" />
          <img src="@/assets/images/logo-ai4ss.png" alt="AI4SS Lab" class="header-logo" />
        </div>
        <h1>AI素养评测平台</h1>
        <p>基于多智能体协同的智能化评测系统</p>
      </div>
      <a-card class="login-card">
        <a-form
          :model="loginForm"
          @finish="handleLogin"
          layout="vertical"
        >
          <a-form-item
            name="username"
            :rules="[{ required: true, message: '请输入用户名' }]"
          >
            <a-input
              v-model:value="loginForm.username"
              placeholder="用户名"
              size="large"
            >
              <template #prefix><UserOutlined /></template>
            </a-input>
          </a-form-item>

          <a-form-item
            name="password"
            :rules="[{ required: true, message: '请输入密码' }]"
          >
            <a-input-password
              v-model:value="loginForm.password"
              placeholder="密码"
              size="large"
            >
              <template #prefix><LockOutlined /></template>
            </a-input-password>
          </a-form-item>

          <a-form-item>
            <a-button
              type="primary"
              html-type="submit"
              size="large"
              block
              :loading="loading"
              class="login-btn"
            >
              登录
            </a-button>
          </a-form-item>

          <div style="text-align: center">
            <router-link to="/register">没有账号？立即注册</router-link>
          </div>
        </a-form>
      </a-card>

      <div class="login-footer">
        云瀚社区与AI4SS实验室版权所有 &copy; 2026
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { UserOutlined, LockOutlined } from '@ant-design/icons-vue'
import { useUserStore } from '@/stores/user'
import request from '@/utils/request'

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)

const loginForm = ref({
  username: '',
  password: '',
})

async function handleLogin() {
  loading.value = true
  try {
    const data: any = await request.post('/auth/login', {
      username: loginForm.value.username,
      password: loginForm.value.password,
    })
    userStore.setToken(data.access_token)
    userStore.setUserInfo({
      id: data.user.id,
      username: data.user.username,
      email: data.user.email,
      full_name: data.user.full_name,
      role: data.user.role,
      is_active: data.user.is_active,
    })
    message.success('登录成功')
    const target = data.user.role === 'examinee' ? 'Exams' : 'Dashboard'
    router.push({ name: target })
  } catch (err: any) {
    // Error already handled by response interceptor
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0F2B46 0%, #1F4E79 40%, #2A6BA6 70%, #3D8ED0 100%);
  position: relative;
  overflow: hidden;
}

/* Decorative floating shapes */
.bg-shape {
  position: absolute;
  border-radius: 50%;
  opacity: 0.06;
  background: #fff;
}

.bg-shape-1 {
  width: 600px;
  height: 600px;
  top: -200px;
  right: -150px;
}

.bg-shape-2 {
  width: 400px;
  height: 400px;
  bottom: -100px;
  left: -100px;
}

.bg-shape-3 {
  width: 200px;
  height: 200px;
  top: 40%;
  left: 15%;
}

.login-container {
  width: 420px;
  position: relative;
  z-index: 1;
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
  color: #fff;
}

.login-logos {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-bottom: 20px;
}

.header-logo {
  height: 52px;
  opacity: 0.95;
}

.login-header h1 {
  font-size: 30px;
  font-weight: 700;
  margin-bottom: 8px;
  letter-spacing: 2px;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.login-header p {
  font-size: 14px;
  opacity: 0.75;
  letter-spacing: 1px;
}

.login-card {
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
  border: none;
}

.login-card :deep(.ant-card-body) {
  padding: 32px;
}

.login-btn {
  height: 44px;
  font-size: 16px;
  font-weight: 600;
  border-radius: 8px;
  background: linear-gradient(135deg, #1F4E79, #2A6BA6);
  border: none;
  box-shadow: 0 4px 12px rgba(31, 78, 121, 0.4);
  transition: all 0.3s;
}

.login-btn:hover {
  background: linear-gradient(135deg, #2A6BA6, #3D8ED0);
  box-shadow: 0 6px 16px rgba(31, 78, 121, 0.5);
  transform: translateY(-1px);
}

.login-footer {
  text-align: center;
  margin-top: 24px;
  color: rgba(255, 255, 255, 0.4);
  font-size: 12px;
}
</style>
