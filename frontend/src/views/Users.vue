<template>
  <div>
    <a-page-header
      :title="archiveMode ? '已删除用户' : '用户管理'"
      :sub-title="archiveMode ? '查看已删除用户及其成绩记录' : '管理平台用户账号'"
    />

    <a-card>
      <!-- 搜索栏 -->
      <div style="display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; align-items: center;">
        <template v-if="!archiveMode">
          <a-input
            v-model:value="searchKeyword"
            placeholder="搜索用户名/邮箱/姓名"
            style="width: 240px"
            allow-clear
            @press-enter="fetchUsers"
          >
            <template #prefix><SearchOutlined /></template>
          </a-input>
          <a-select
            v-model:value="filterRole"
            placeholder="角色筛选"
            style="width: 140px"
            allow-clear
            @change="fetchUsers"
          >
            <a-select-option value="admin">管理员</a-select-option>
            <a-select-option value="organizer">组织者</a-select-option>
            <a-select-option value="examinee">被测者</a-select-option>
            <a-select-option value="reviewer">审题员</a-select-option>
          </a-select>
          <a-select
            v-model:value="filterActive"
            placeholder="状态筛选"
            style="width: 140px"
            allow-clear
            @change="fetchUsers"
          >
            <a-select-option value="true">已启用</a-select-option>
            <a-select-option value="false">待审批/禁用</a-select-option>
          </a-select>
          <a-button type="primary" @click="showAddModal">
            <PlusOutlined /> 添加用户
          </a-button>
          <a-button @click="importModalVisible = true">
            <UploadOutlined /> 批量导入
          </a-button>
        </template>
        <div style="flex: 1; text-align: right;">
          <a-button v-if="!archiveMode" @click="enterArchiveMode">
            <template #icon><DeleteOutlined /></template>
            已删除用户
          </a-button>
          <a-button v-else @click="exitArchiveMode">
            <template #icon><RollbackOutlined /></template>
            返回用户管理
          </a-button>
        </div>
      </div>

      <!-- 用户表格 -->
      <a-table
        :columns="currentColumns"
        :data-source="users"
        :loading="loading"
        :pagination="{ total, current: page, pageSize, onChange: onPageChange }"
        row-key="id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'role'">
            <a-tag :color="roleColor(record.role)">{{ roleLabel(record.role) }}</a-tag>
          </template>
          <template v-if="column.key === 'is_active'">
            <a-tag v-if="record.is_active" color="green">已启用</a-tag>
            <a-tag v-else-if="isPendingApproval(record)" color="orange">待审批</a-tag>
            <a-tag v-else color="red">禁用</a-tag>
          </template>
          <template v-if="column.key === 'deleted_at'">
            {{ record.deleted_at ? new Date(record.deleted_at).toLocaleString('zh-CN') : '-' }}
          </template>
          <template v-if="column.key === 'actions'">
            <a-space v-if="archiveMode">
              <a-popconfirm
                title="确定恢复该用户？恢复后用户将恢复正常使用。"
                @confirm="restoreUser(record)"
              >
                <a-button size="small" type="primary">恢复</a-button>
              </a-popconfirm>
              <a-button size="small" @click="viewUserScores(record)">查看成绩</a-button>
            </a-space>
            <a-space v-else>
              <a-popconfirm
                v-if="isPendingApproval(record)"
                title="确定通过该用户的注册审批？"
                @confirm="approveUser(record)"
              >
                <a-button size="small" type="primary" style="background: #52c41a; border-color: #52c41a">通过审批</a-button>
              </a-popconfirm>
              <a-button size="small" @click="showEditModal(record)">编辑</a-button>
              <a-button size="small" @click="showResetPasswordModal(record)">重置密码</a-button>
              <a-popconfirm
                v-if="record.id !== userStore.userInfo?.id"
                :title="record.is_active ? '确定禁用该用户？' : '确定启用该用户？'"
                @confirm="toggleActive(record)"
              >
                <a-button size="small" :danger="record.is_active">
                  {{ record.is_active ? '禁用' : '启用' }}
                </a-button>
              </a-popconfirm>
              <a-popconfirm
                v-if="record.role !== 'admin'"
                title="确定删除该用户？删除后用户将无法登录，数据归入已删除存档。"
                @confirm="deleteUser(record)"
              >
                <a-button size="small" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 添加/编辑用户弹窗 -->
    <a-modal
      v-model:open="modalVisible"
      :title="editingUser ? '编辑用户' : '添加用户'"
      @ok="handleSubmit"
      :confirm-loading="submitting"
    >
      <a-form :model="form" layout="vertical">
        <a-form-item label="用户名" required v-if="!editingUser">
          <a-input v-model:value="form.username" placeholder="请输入用户名" />
        </a-form-item>
        <a-form-item label="用户名" v-if="editingUser">
          <a-input :value="editingUser.username" disabled />
        </a-form-item>
        <a-form-item label="邮箱" required v-if="!editingUser">
          <a-input v-model:value="form.email" placeholder="请输入邮箱" />
        </a-form-item>
        <a-form-item label="密码" required v-if="!editingUser">
          <a-input-password v-model:value="form.password" placeholder="请输入密码（至少6位）" />
        </a-form-item>
        <a-form-item label="姓名">
          <a-input v-model:value="form.full_name" placeholder="请输入姓名" />
        </a-form-item>
        <a-form-item label="手机号">
          <a-input v-model:value="form.phone" placeholder="请输入手机号" />
        </a-form-item>
        <a-form-item label="所属机构">
          <a-input v-model:value="form.organization" placeholder="请输入所属机构" />
        </a-form-item>
        <a-form-item label="角色" required>
          <a-select v-model:value="form.role">
            <a-select-option value="admin">管理员</a-select-option>
            <a-select-option value="organizer">组织者</a-select-option>
            <a-select-option value="examinee">被测者</a-select-option>
            <a-select-option value="reviewer">审题员</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 重置密码弹窗 -->
    <a-modal
      v-model:open="resetModalVisible"
      title="重置密码"
      @ok="handleResetPassword"
      :confirm-loading="submitting"
    >
      <p>为用户 <strong>{{ resetUser?.username }}</strong> 设置新密码：</p>
      <a-input-password v-model:value="newPassword" placeholder="请输入新密码（至少6位）" />
    </a-modal>

    <!-- 成绩查看抽屉 -->
    <a-drawer
      v-model:open="scoreDrawerVisible"
      :title="`${scoreDrawerUser?.full_name || scoreDrawerUser?.username || ''} 的考试记录`"
      width="640"
    >
      <a-table
        :columns="scoreColumns"
        :data-source="scoreDrawerData"
        :loading="scoreDrawerLoading"
        :pagination="false"
        size="small"
        row-key="answer_sheet_id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'total_score'">
            <template v-if="record.total_score != null">
              <span style="font-weight: bold">{{ record.total_score }}</span>
              <span style="color: #999"> / {{ record.max_score }}</span>
            </template>
            <span v-else style="color: #999">-</span>
          </template>
          <template v-if="column.key === 'level'">
            <a-tag v-if="record.level" :color="levelColor(record.level)">{{ record.level }}</a-tag>
            <span v-else style="color: #999">-</span>
          </template>
          <template v-if="column.key === 'submit_time'">
            {{ record.submit_time ? new Date(record.submit_time).toLocaleString('zh-CN') : '-' }}
          </template>
        </template>
      </a-table>
      <a-empty v-if="!scoreDrawerLoading && scoreDrawerData.length === 0" description="暂无考试记录" />
    </a-drawer>

    <!-- 批量导入弹窗 -->
    <a-modal
      v-model:open="importModalVisible"
      title="批量导入被测者"
      :footer="null"
      :maskClosable="false"
      width="560px"
      @cancel="resetImport"
    >
      <template v-if="!importResult">
        <a-alert
          type="info"
          show-icon
          style="margin-bottom: 16px"
        >
          <template #message>
            上传 Excel (.xlsx) 或 CSV 文件，需包含 <strong>username（用户名）</strong>和 <strong>email（邮箱）</strong>列。
            导入的用户角色为「被测者」，初始密码为 <code>abcdefg</code>。
          </template>
        </a-alert>
        <div style="margin-bottom: 16px">
          <a-button type="link" style="padding: 0" @click="downloadTemplate">
            <DownloadOutlined /> 下载导入模板
          </a-button>
        </div>
        <a-upload-dragger
          :file-list="importFileList"
          :before-upload="beforeImportUpload"
          :max-count="1"
          accept=".xlsx,.csv"
          @remove="importFileList = []"
        >
          <p class="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p class="ant-upload-text">点击或拖拽文件到此区域上传</p>
          <p class="ant-upload-hint">支持 .xlsx 和 .csv 格式</p>
        </a-upload-dragger>
        <div style="margin-top: 16px; text-align: right;">
          <a-button @click="importModalVisible = false" style="margin-right: 8px">取消</a-button>
          <a-button type="primary" :loading="importLoading" :disabled="importFileList.length === 0" @click="handleImport">
            开始导入
          </a-button>
        </div>
      </template>

      <template v-else>
        <a-result
          :status="importResult.failed === 0 ? 'success' : 'warning'"
          :title="`成功导入 ${importResult.successful} 个用户${importResult.failed > 0 ? `，${importResult.failed} 个失败` : ''}`"
        >
          <template #extra>
            <a-button type="primary" @click="resetImport">继续导入</a-button>
            <a-button @click="importModalVisible = false; resetImport()">关闭</a-button>
          </template>
        </a-result>
        <a-table
          v-if="importResult.errors.length > 0"
          :columns="importErrorColumns"
          :data-source="importResult.errors"
          :pagination="false"
          size="small"
          row-key="row"
          style="margin-top: 16px"
        >
        </a-table>
      </template>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { SearchOutlined, PlusOutlined, DeleteOutlined, RollbackOutlined, UploadOutlined, InboxOutlined, DownloadOutlined } from '@ant-design/icons-vue'
import request from '@/utils/request'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()

// --- Archive mode ---
const archiveMode = ref(false)

// --- Columns ---
const normalColumns = [
  { title: '用户名', dataIndex: 'username', key: 'username' },
  { title: '姓名', dataIndex: 'full_name', key: 'full_name' },
  { title: '邮箱', dataIndex: 'email', key: 'email' },
  { title: '角色', key: 'role' },
  { title: '状态', key: 'is_active', width: 80 },
  { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180,
    customRender: ({ text }: { text: string }) => text ? new Date(text).toLocaleString('zh-CN') : '-' },
  { title: '操作', key: 'actions', width: 280 },
]

const archiveColumns = [
  { title: '用户名', dataIndex: 'username', key: 'username' },
  { title: '姓名', dataIndex: 'full_name', key: 'full_name' },
  { title: '邮箱', dataIndex: 'email', key: 'email' },
  { title: '角色', key: 'role' },
  { title: '删除时间', key: 'deleted_at', width: 180 },
  { title: '操作', key: 'actions', width: 180 },
]

const currentColumns = computed(() => archiveMode.value ? archiveColumns : normalColumns)

// --- Score drawer columns ---
const scoreColumns = [
  { title: '考试名称', dataIndex: 'exam_title', key: 'exam_title', ellipsis: true },
  { title: '得分', key: 'total_score', width: 120 },
  { title: '等级', key: 'level', width: 90 },
  { title: '提交时间', key: 'submit_time', width: 180 },
]

// --- State ---
const users = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const searchKeyword = ref('')
const filterRole = ref<string | undefined>(undefined)
const filterActive = ref<string | undefined>(undefined)

const modalVisible = ref(false)
const editingUser = ref<any>(null)
const submitting = ref(false)
const form = ref({
  username: '',
  email: '',
  password: '',
  full_name: '',
  phone: '',
  organization: '',
  role: 'examinee',
})

const resetModalVisible = ref(false)
const resetUser = ref<any>(null)
const newPassword = ref('')

// Score drawer
const scoreDrawerVisible = ref(false)
const scoreDrawerUser = ref<any>(null)
const scoreDrawerData = ref<any[]>([])
const scoreDrawerLoading = ref(false)

// Batch import
const importModalVisible = ref(false)
const importLoading = ref(false)
const importFileList = ref<any[]>([])
const importResult = ref<any>(null)

const importErrorColumns = [
  { title: '行号', dataIndex: 'row', key: 'row', width: 70 },
  { title: '用户名', dataIndex: 'username', key: 'username' },
  { title: '邮箱', dataIndex: 'email', key: 'email' },
  { title: '错误原因', dataIndex: 'error', key: 'error' },
]

// --- Helpers ---
function roleLabel(role: string) {
  const map: Record<string, string> = { admin: '管理员', organizer: '组织者', examinee: '被测者', reviewer: '审题员' }
  return map[role] || role
}

function roleColor(role: string) {
  const map: Record<string, string> = { admin: 'red', organizer: 'blue', examinee: 'green', reviewer: 'orange' }
  return map[role] || 'default'
}

function levelColor(level: string) {
  const map: Record<string, string> = { '优秀': 'green', '良好': 'blue', '合格': 'orange', '不合格': 'red' }
  return map[level] || 'default'
}

function isPendingApproval(record: any): boolean {
  return !record.is_active && ['organizer', 'reviewer'].includes(record.role)
}

// --- Data fetching ---
async function fetchUsers() {
  loading.value = true
  try {
    const params: any = {
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
    }
    if (archiveMode.value) {
      params.archive = true
    } else {
      if (searchKeyword.value) params.keyword = searchKeyword.value
      if (filterRole.value) params.role = filterRole.value
      if (filterActive.value !== undefined) params.is_active = filterActive.value
    }

    const data: any = await request.get('/users', { params })
    users.value = data.items
    total.value = data.total
  } catch (err) {
    // handled by interceptor
  } finally {
    loading.value = false
  }
}

function onPageChange(p: number) {
  page.value = p
  fetchUsers()
}

// --- Archive mode ---
function enterArchiveMode() {
  archiveMode.value = true
  page.value = 1
  fetchUsers()
}

function exitArchiveMode() {
  archiveMode.value = false
  page.value = 1
  fetchUsers()
}

// --- Restore user ---
async function restoreUser(record: any) {
  try {
    await request.post(`/users/${record.id}/restore`)
    message.success(`用户 ${record.username} 已恢复`)
    fetchUsers()
  } catch (err) {
    // handled by interceptor
  }
}

// --- Delete user ---
async function deleteUser(record: any) {
  try {
    await request.delete(`/users/${record.id}`)
    message.success(`用户 ${record.username} 已删除`)
    fetchUsers()
  } catch (err) {
    // handled by interceptor
  }
}

// --- View user scores ---
async function viewUserScores(record: any) {
  scoreDrawerUser.value = record
  scoreDrawerVisible.value = true
  scoreDrawerLoading.value = true
  try {
    const data: any = await request.get(`/users/${record.id}/scores`)
    scoreDrawerData.value = data.items || []
  } catch (err) {
    scoreDrawerData.value = []
  } finally {
    scoreDrawerLoading.value = false
  }
}

// --- CRUD ---
function showAddModal() {
  editingUser.value = null
  form.value = { username: '', email: '', password: '', full_name: '', phone: '', organization: '', role: 'examinee' }
  modalVisible.value = true
}

function showEditModal(record: any) {
  editingUser.value = record
  form.value = {
    username: record.username,
    email: record.email,
    password: '',
    full_name: record.full_name || '',
    phone: record.phone || '',
    organization: record.organization || '',
    role: record.role,
  }
  modalVisible.value = true
}

async function handleSubmit() {
  submitting.value = true
  try {
    if (editingUser.value) {
      await request.put(`/users/${editingUser.value.id}`, {
        full_name: form.value.full_name || null,
        phone: form.value.phone || null,
        organization: form.value.organization || null,
        role: form.value.role,
      })
      message.success('用户信息更新成功')
    } else {
      if (!form.value.username || !form.value.email || !form.value.password) {
        message.error('请填写必填项')
        return
      }
      await request.post('/users', form.value)
      message.success('用户创建成功')
    }
    modalVisible.value = false
    fetchUsers()
  } catch (err) {
    // handled by interceptor
  } finally {
    submitting.value = false
  }
}

function showResetPasswordModal(record: any) {
  resetUser.value = record
  newPassword.value = ''
  resetModalVisible.value = true
}

async function handleResetPassword() {
  if (!newPassword.value || newPassword.value.length < 6) {
    message.error('密码长度不能少于6位')
    return
  }
  submitting.value = true
  try {
    await request.post(`/users/${resetUser.value.id}/reset-password`, {
      new_password: newPassword.value,
    })
    message.success('密码重置成功')
    resetModalVisible.value = false
  } catch (err) {
    // handled by interceptor
  } finally {
    submitting.value = false
  }
}

async function approveUser(record: any) {
  try {
    await request.put(`/users/${record.id}`, { is_active: true })
    message.success(`已通过 ${record.username} 的注册审批`)
    fetchUsers()
  } catch (err) {
    // handled by interceptor
  }
}

async function toggleActive(record: any) {
  try {
    await request.put(`/users/${record.id}`, { is_active: !record.is_active })
    message.success(record.is_active ? '已禁用' : '已启用')
    fetchUsers()
  } catch (err) {
    // handled by interceptor
  }
}

// --- Batch import ---
function beforeImportUpload(file: any) {
  importFileList.value = [file]
  return false  // prevent auto-upload
}

async function handleImport() {
  if (importFileList.value.length === 0) return
  importLoading.value = true
  try {
    const formData = new FormData()
    formData.append('file', importFileList.value[0] as any)
    const data: any = await request.post('/users/batch-import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    importResult.value = data
    if (data.successful > 0) {
      fetchUsers()
    }
  } catch (err) {
    message.error('导入失败，请检查文件格式')
  } finally {
    importLoading.value = false
  }
}

function downloadTemplate() {
  const csv = 'username,email\n'
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = '用户导入模板.csv'
  link.click()
  URL.revokeObjectURL(url)
}

function resetImport() {
  importFileList.value = []
  importResult.value = null
  importLoading.value = false
}

onMounted(fetchUsers)
</script>
