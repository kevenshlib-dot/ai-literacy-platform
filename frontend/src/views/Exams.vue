<template>
  <div class="page-container">
    <div class="page-header">
      <h2>{{ archiveMode ? '已关闭试卷' : '考试管理' }}</h2>
      <a-space>
        <a-button v-if="archiveMode" @click="exitArchiveMode">
          <template #icon><RollbackOutlined /></template>
          返回管理
        </a-button>
        <a-button v-if="!archiveMode" type="primary" @click="showCreateModal">
          <template #icon><PlusOutlined /></template>
          创建考试
        </a-button>
      </a-space>
    </div>

    <!-- Filter Bar (hidden in archive mode) -->
    <a-card v-if="!archiveMode" class="filter-card" :bordered="false">
      <a-row :gutter="16">
        <a-col :span="6">
          <a-input v-model:value="filters.keyword" placeholder="搜索考试名称" allow-clear @press-enter="fetchExams">
            <template #prefix><SearchOutlined /></template>
          </a-input>
        </a-col>
        <a-col :span="4">
          <a-select v-model:value="filters.status" placeholder="状态筛选" allow-clear style="width: 100%">
            <a-select-option value="draft">草稿</a-select-option>
            <a-select-option value="published">已发布</a-select-option>
            <a-select-option value="closed">已关闭</a-select-option>
          </a-select>
        </a-col>
        <a-col :span="4">
          <a-button type="primary" @click="fetchExams">查询</a-button>
          <a-button style="margin-left: 8px" @click="resetFilters">重置</a-button>
        </a-col>
        <a-col :flex="1" style="text-align: right">
          <a-button @click="enterArchiveMode">
            <template #icon><FolderOutlined /></template>
            已关闭试卷
          </a-button>
        </a-col>
      </a-row>
    </a-card>

    <!-- Exam Table -->
    <a-card class="card-container" :bordered="false">
      <a-table
        :columns="columns"
        :data-source="exams"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template v-if="column.key === 'time_limit'">
            {{ record.time_limit_minutes ? record.time_limit_minutes + ' 分钟' : '不限时' }}
          </template>
          <template v-if="column.key === 'questions'">
            {{ record._question_count ?? '-' }}
          </template>
          <template v-if="column.key === 'created_at'">
            {{ formatDate(record.created_at) }}
          </template>
          <template v-if="column.key === 'actions'">
            <a-space v-if="archiveMode">
              <a @click="viewExam(record)">详情</a>
              <a-popconfirm title='确定重新激活该试卷为「已发布」状态？' @confirm="reactivateExam(record)">
                <a style="color: #52c41a">重新发布</a>
              </a-popconfirm>
              <a-popconfirm title="确定删除此试卷？" @confirm="deleteExam(record)">
                <a style="color: #ff4d4f">删除</a>
              </a-popconfirm>
            </a-space>
            <a-space v-else>
              <a @click="viewExam(record)">详情</a>
              <a @click="showEditModal(record)" v-if="record.status === 'draft'">编辑</a>
              <a @click="openComposer(record)" v-if="record.status === 'draft'">编排</a>
              <a @click="showAssembleModal(record)" v-if="record.status === 'draft'">组卷</a>
              <a-popconfirm title="确定发布此考试？" @confirm="publishExam(record)" v-if="record.status === 'draft'">
                <a style="color: #52c41a">发布</a>
              </a-popconfirm>
              <a-popconfirm title="确定关闭此考试？" @confirm="closeExam(record)" v-if="record.status === 'published'">
                <a style="color: #faad14">关闭</a>
              </a-popconfirm>
              <a-popconfirm title="确定删除此考试？" @confirm="deleteExam(record)" v-if="record.status === 'draft'">
                <a style="color: #ff4d4f">删除</a>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Create/Edit Modal -->
    <a-modal
      v-model:open="formModal.visible"
      :title="formModal.isEdit ? '编辑考试' : '创建考试'"
      @ok="handleFormSubmit"
      :confirm-loading="formModal.loading"
    >
      <a-form :model="formModal.data" layout="vertical">
        <a-form-item label="考试名称" required>
          <a-input v-model:value="formModal.data.title" placeholder="请输入考试名称" />
        </a-form-item>
        <a-form-item label="考试描述">
          <a-textarea v-model:value="formModal.data.description" placeholder="请输入考试描述" :rows="3" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="考试时长（分钟）">
              <a-input-number v-model:value="formModal.data.time_limit_minutes" :min="1" :max="300" placeholder="不限时" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="总分">
              <a-input-number v-model:value="formModal.data.total_score" :min="1" :max="1000" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>

    <!-- Auto-Assemble Modal -->
    <a-modal
      v-model:open="assembleModal.visible"
      title="智能组卷"
      width="640px"
      @ok="handleAssemble"
      :confirm-loading="assembleModal.loading"
    >
      <a-alert
        v-if="approvedCount === 0"
        type="warning"
        show-icon
        message="题库中暂无已审核通过的题目，请先在题库管理中审核题目"
        style="margin-bottom: 16px"
      />
      <a-alert
        v-else
        type="info"
        :message="`题库中共有 ${approvedCount} 道已审核题目可供组卷`"
        style="margin-bottom: 16px"
      />
      <a-form layout="vertical">
        <a-form-item label="题型分配">
          <a-row :gutter="[8, 8]">
            <a-col :span="8">
              <a-input-number v-model:value="typeDist.single_choice" :min="0" :max="50" addon-before="单选题" style="width: 100%" />
            </a-col>
            <a-col :span="8">
              <a-input-number v-model:value="typeDist.multiple_choice" :min="0" :max="50" addon-before="多选题" style="width: 100%" />
            </a-col>
            <a-col :span="8">
              <a-input-number v-model:value="typeDist.true_false" :min="0" :max="50" addon-before="判断题" style="width: 100%" />
            </a-col>
            <a-col :span="8">
              <a-input-number v-model:value="typeDist.fill_blank" :min="0" :max="50" addon-before="填空题" style="width: 100%" />
            </a-col>
            <a-col :span="8">
              <a-input-number v-model:value="typeDist.short_answer" :min="0" :max="50" addon-before="简答题" style="width: 100%" />
            </a-col>
          </a-row>
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="目标难度">
              <a-slider v-model:value="assembleModal.data.difficulty_target" :min="1" :max="5" :marks="{1:'简单',3:'中等',5:'困难'}" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="难度容差">
              <a-input-number v-model:value="assembleModal.data.difficulty_tolerance" :min="0" :max="2" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="每题分值">
              <a-input-number v-model:value="assembleModal.data.score_per_question" :min="1" :max="50" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="知识维度（可选）">
          <a-select v-model:value="assembleModal.data.dimensions" mode="multiple" placeholder="不限维度" style="width: 100%">
            <a-select-option value="AI基础知识">AI基础知识</a-select-option>
            <a-select-option value="AI技术应用">AI技术应用</a-select-option>
            <a-select-option value="AI伦理安全">AI伦理安全</a-select-option>
            <a-select-option value="AI批判思维">AI批判思维</a-select-option>
            <a-select-option value="AI创新实践">AI创新实践</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- Exam Detail Drawer -->
    <a-drawer
      v-model:open="detailDrawer.visible"
      :title="detailDrawer.exam?.title || '考试详情'"
      width="720"
    >
      <template v-if="detailDrawer.exam">
        <a-descriptions :column="2" bordered size="small">
          <a-descriptions-item label="状态">
            <a-tag :color="statusColor(detailDrawer.exam.status)">{{ statusLabel(detailDrawer.exam.status) }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="总分">{{ detailDrawer.exam.total_score }}</a-descriptions-item>
          <a-descriptions-item label="时长">{{ detailDrawer.exam.time_limit_minutes ? detailDrawer.exam.time_limit_minutes + ' 分钟' : '不限时' }}</a-descriptions-item>
          <a-descriptions-item label="使用次数">{{ detailDrawer.exam.usage_count }}</a-descriptions-item>
          <a-descriptions-item label="描述" :span="2">{{ detailDrawer.exam.description || '无' }}</a-descriptions-item>
        </a-descriptions>

        <a-divider>试题列表（{{ detailDrawer.questions.length }} 题）</a-divider>

        <a-table
          :columns="questionColumns"
          :data-source="detailDrawer.questions"
          :pagination="false"
          size="small"
          row-key="id"
        >
          <template #bodyCell="{ column, record, index }">
            <template v-if="column.key === 'order'">{{ index + 1 }}</template>
            <template v-if="column.key === 'score'">{{ record.score }} 分</template>
          </template>
        </a-table>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { PlusOutlined, SearchOutlined, FolderOutlined, RollbackOutlined } from '@ant-design/icons-vue'
import request from '@/utils/request'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const exams = ref<any[]>([])
const archiveMode = ref(false)
const filters = reactive({ keyword: '', status: undefined as string | undefined })
const pagination = reactive({ current: 1, pageSize: 20, total: 0 })

const approvedCount = ref(0)

const typeDist = reactive({
  single_choice: 10,
  multiple_choice: 0,
  true_false: 5,
  fill_blank: 0,
  short_answer: 0,
})

const columns = [
  { title: '考试名称', dataIndex: 'title', key: 'title', ellipsis: true },
  { title: '状态', key: 'status', width: 100 },
  { title: '总分', dataIndex: 'total_score', key: 'total_score', width: 80 },
  { title: '时长', key: 'time_limit', width: 100 },
  { title: '使用次数', dataIndex: 'usage_count', key: 'usage_count', width: 90 },
  { title: '创建时间', key: 'created_at', width: 160 },
  { title: '操作', key: 'actions', width: 260, fixed: 'right' },
]

const questionColumns = [
  { title: '序号', key: 'order', width: 60 },
  { title: '题目ID', dataIndex: 'question_id', key: 'question_id', ellipsis: true },
  { title: '分值', key: 'score', width: 80 },
]

// Form modal
const formModal = reactive({
  visible: false,
  isEdit: false,
  loading: false,
  editId: null as string | null,
  data: { title: '', description: '', time_limit_minutes: null as number | null, total_score: 100 },
})

// Assemble modal
const assembleModal = reactive({
  visible: false,
  loading: false,
  examId: null as string | null,
  data: {
    difficulty_target: 3,
    difficulty_tolerance: 1,
    score_per_question: 5,
    dimensions: [] as string[],
  },
})

// Detail drawer
const detailDrawer = reactive({
  visible: false,
  exam: null as any,
  questions: [] as any[],
})

function statusColor(s: string) {
  return { draft: 'default', published: 'green', closed: 'orange' }[s] || 'default'
}
function statusLabel(s: string) {
  return { draft: '草稿', published: '已发布', closed: '已关闭' }[s] || s
}
function formatDate(d: string) {
  if (!d) return ''
  return new Date(d).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function parsePositiveInt(value: unknown, fallback: number) {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback
}

function applyRouteState() {
  archiveMode.value = route.query.archive === '1'
  filters.keyword = typeof route.query.keyword === 'string' ? route.query.keyword : ''
  filters.status = typeof route.query.status === 'string' ? route.query.status : undefined
  pagination.current = parsePositiveInt(route.query.page, 1)
  pagination.pageSize = parsePositiveInt(route.query.page_size, 20)
}

function buildRouteQuery() {
  const query: Record<string, string> = {}
  if (archiveMode.value) {
    query.archive = '1'
  } else {
    if (filters.keyword) query.keyword = filters.keyword
    if (filters.status) query.status = filters.status
  }
  if (pagination.current > 1) query.page = String(pagination.current)
  if (pagination.pageSize !== 20) query.page_size = String(pagination.pageSize)
  return query
}

async function fetchExams(syncRoute = true) {
  loading.value = true
  try {
    if (syncRoute) {
      await router.replace({ name: 'Exams', query: buildRouteQuery() })
    }
    const params: any = { skip: (pagination.current - 1) * pagination.pageSize, limit: pagination.pageSize }
    if (archiveMode.value) {
      params.archive = true
    } else {
      params.is_random_test = false
      if (filters.keyword) params.keyword = filters.keyword
      if (filters.status) params.status = filters.status
    }
    const data: any = await request.get('/exams', { params })
    exams.value = data.items || []
    pagination.total = data.total || 0
  } catch { /* handled by interceptor */ } finally {
    loading.value = false
  }
}

function enterArchiveMode() {
  archiveMode.value = true
  filters.keyword = ''
  filters.status = undefined
  pagination.current = 1
  fetchExams()
}

function exitArchiveMode() {
  archiveMode.value = false
  pagination.current = 1
  fetchExams()
}

function handleTableChange(pag: any) {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  fetchExams()
}

function resetFilters() {
  filters.keyword = ''
  filters.status = undefined
  pagination.current = 1
  fetchExams()
}

function showCreateModal() {
  formModal.isEdit = false
  formModal.editId = null
  formModal.data = { title: '', description: '', time_limit_minutes: null, total_score: 100 }
  formModal.visible = true
}

function showEditModal(record: any) {
  formModal.isEdit = true
  formModal.editId = record.id
  formModal.data = {
    title: record.title,
    description: record.description || '',
    time_limit_minutes: record.time_limit_minutes,
    total_score: record.total_score,
  }
  formModal.visible = true
}

function openComposer(record: any) {
  router.push({
    name: 'ExamCompose',
    params: { examId: record.id },
    query: { returnTo: route.fullPath },
  })
}

async function handleFormSubmit() {
  if (!formModal.data.title) {
    message.warning('请输入考试名称')
    return
  }
  formModal.loading = true
  try {
    const payload: any = { ...formModal.data }
    if (!payload.time_limit_minutes) delete payload.time_limit_minutes
    if (formModal.isEdit) {
      await request.put(`/exams/${formModal.editId}`, payload)
      message.success('更新成功')
    } else {
      await request.post('/exams', payload)
      message.success('创建成功')
    }
    formModal.visible = false
    fetchExams()
  } catch { /* handled */ } finally {
    formModal.loading = false
  }
}

async function showAssembleModal(record: any) {
  assembleModal.examId = record.id
  assembleModal.data = {
    difficulty_target: 3,
    difficulty_tolerance: 1,
    score_per_question: 5,
    dimensions: [],
  }
  typeDist.single_choice = 10
  typeDist.multiple_choice = 0
  typeDist.true_false = 5
  typeDist.fill_blank = 0
  typeDist.short_answer = 0
  assembleModal.visible = true
  // Fetch approved question count
  try {
    const data: any = await request.get('/questions', { params: { status: 'approved', skip: 0, limit: 1 } })
    approvedCount.value = data.total || 0
  } catch { approvedCount.value = 0 }
}

async function handleAssemble() {
  const dist: Record<string, number> = {}
  for (const [k, v] of Object.entries(typeDist)) {
    if (v > 0) dist[k] = v
  }
  if (Object.keys(dist).length === 0) {
    message.warning('请至少设置一种题型的数量')
    return
  }
  assembleModal.loading = true
  try {
    const payload: any = {
      type_distribution: dist,
      difficulty_target: assembleModal.data.difficulty_target,
      difficulty_tolerance: assembleModal.data.difficulty_tolerance,
      score_per_question: assembleModal.data.score_per_question,
    }
    if (assembleModal.data.dimensions.length > 0) {
      payload.dimensions = assembleModal.data.dimensions
    }
    const data: any = await request.post(`/exams/${assembleModal.examId}/assemble/auto`, payload)
    if (data.total_questions === 0) {
      message.warning('组卷结果为空：题库中没有符合条件的已审核题目，请先在题库管理中审核通过题目')
    } else {
      message.success(`组卷成功！共 ${data.total_questions} 题，总分 ${data.total_score}`)
      assembleModal.visible = false
    }
    fetchExams()
  } catch { /* handled */ } finally {
    assembleModal.loading = false
  }
}

async function viewExam(record: any) {
  try {
    const data: any = await request.get(`/exams/${record.id}`)
    detailDrawer.exam = data
    detailDrawer.questions = data.questions || []
    detailDrawer.visible = true
  } catch { /* handled */ }
}

async function publishExam(record: any) {
  try {
    await request.post(`/exams/${record.id}/publish`)
    message.success('发布成功')
    fetchExams()
  } catch { /* handled */ }
}

async function closeExam(record: any) {
  try {
    await request.post(`/exams/${record.id}/close`)
    message.success('已关闭')
    fetchExams()
  } catch { /* handled */ }
}

async function reactivateExam(record: any) {
  try {
    await request.post(`/exams/${record.id}/reactivate`)
    message.success('试卷已重新发布')
    fetchExams()
  } catch { /* handled */ }
}

async function deleteExam(record: any) {
  try {
    await request.delete(`/exams/${record.id}`)
    message.success('已删除')
    fetchExams()
  } catch { /* handled */ }
}

onMounted(() => {
  applyRouteState()
  fetchExams(false)
})
</script>

<style scoped>
.filter-card { margin-bottom: 16px; }
</style>
