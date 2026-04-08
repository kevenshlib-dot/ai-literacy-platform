<template>
  <div class="login-page">
    <div class="login-container">
      <div class="login-header">
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
            >
              登录
            </a-button>
          </a-form-item>

          <div style="text-align: center">
            <router-link to="/register">没有账号？立即注册</router-link>
          </div>
        </a-form>
      </a-card>
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
    // Examinees go straight to exam page, others to dashboard
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
  background: linear-gradient(135deg, #1F4E79 0%, #2A6BA6 50%, #3D8ED0 100%);
}

.login-container {
  width: 400px;
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
  color: #fff;
}

.login-header h1 {
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 8px;
}

.login-header p {
  font-size: 14px;
  opacity: 0.85;
}

.login-card {
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}
</style>
