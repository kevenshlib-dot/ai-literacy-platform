<template>
  <div class="login-page">
    <div class="login-container">
      <div class="login-header">
        <h1>AI素养评测平台</h1>
        <p>用户注册</p>
      </div>
      <a-card class="login-card">
        <a-form
          :model="form"
          @finish="handleRegister"
          layout="vertical"
        >
          <a-form-item
            name="username"
            :rules="[{ required: true, message: '请输入用户名' }]"
          >
            <a-input
              v-model:value="form.username"
              placeholder="用户名"
              size="large"
            >
              <template #prefix><UserOutlined /></template>
            </a-input>
          </a-form-item>

          <a-form-item
            name="email"
            :rules="[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '请输入有效的邮箱地址' },
            ]"
          >
            <a-input
              v-model:value="form.email"
              placeholder="邮箱（必填，用于接收通知）"
              size="large"
            >
              <template #prefix><MailOutlined /></template>
            </a-input>
          </a-form-item>

          <a-form-item
            name="password"
            :rules="[
              { required: true, message: '请输入密码' },
              { min: 6, message: '密码长度不能少于6位' },
            ]"
          >
            <a-input-password
              v-model:value="form.password"
              placeholder="密码（至少6位）"
              size="large"
            >
              <template #prefix><LockOutlined /></template>
            </a-input-password>
          </a-form-item>

          <a-form-item
            name="confirmPassword"
            :rules="[
              { required: true, message: '请确认密码' },
              { validator: validateConfirmPassword },
            ]"
          >
            <a-input-password
              v-model:value="form.confirmPassword"
              placeholder="确认密码"
              size="large"
            >
              <template #prefix><LockOutlined /></template>
            </a-input-password>
          </a-form-item>

          <a-form-item name="full_name">
            <a-input
              v-model:value="form.full_name"
              placeholder="姓名（选填）"
              size="large"
            >
              <template #prefix><IdcardOutlined /></template>
            </a-input>
          </a-form-item>

          <a-form-item name="role" label="注册角色">
            <a-radio-group v-model:value="form.role" button-style="solid" size="large" style="width: 100%">
              <a-radio-button value="examinee" style="width: 33.33%; text-align: center">被测者</a-radio-button>
              <a-radio-button value="organizer" style="width: 33.33%; text-align: center">组织者</a-radio-button>
              <a-radio-button value="reviewer" style="width: 33.33%; text-align: center">审题员</a-radio-button>
            </a-radio-group>
          </a-form-item>

          <a-alert
            v-if="form.role !== 'examinee'"
            message="注册后需等待管理员审批，审批通过后方可使用系统"
            type="info"
            show-icon
            style="margin-bottom: 16px"
          />

          <a-form-item>
            <a-button
              type="primary"
              html-type="submit"
              size="large"
              block
              :loading="loading"
            >
              注册
            </a-button>
          </a-form-item>

          <div style="text-align: center">
            <router-link to="/login">已有账号？返回登录</router-link>
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
import { UserOutlined, LockOutlined, MailOutlined, IdcardOutlined } from '@ant-design/icons-vue'
import { useUserStore } from '@/stores/user'
import request from '@/utils/request'

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)

const form = ref({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
  full_name: '',
  role: 'examinee',
})

function validateConfirmPassword(_rule: any, value: string) {
  if (value && value !== form.value.password) {
    return Promise.reject('两次输入的密码不一致')
  }
  return Promise.resolve()
}

async function handleRegister() {
  loading.value = true
  try {
    const data: any = await request.post('/auth/register', {
      username: form.value.username,
      email: form.value.email,
      password: form.value.password,
      full_name: form.value.full_name || undefined,
      role: form.value.role,
    })

    if (data.needs_approval) {
      message.success(data.message || '注册成功，请等待管理员审批通知')
      setTimeout(() => {
        router.push({ name: 'Login' })
      }, 2000)
    } else {
      userStore.setToken(data.access_token)
      userStore.setUserInfo({
        id: data.user.id,
        username: data.user.username,
        email: data.user.email,
        full_name: data.user.full_name,
        role: data.user.role,
        is_active: data.user.is_active,
      })
      message.success('注册成功')
      router.push({ name: 'TakeExam' })
    }
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
  width: 440px;
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
