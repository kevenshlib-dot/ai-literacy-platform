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
      width="760px"
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
        <a-form-item label="面向人员类型">
          <a-radio-group v-model:value="assembleModal.data.audience_type" @change="handleAudienceTypeChange">
            <a-radio-button v-for="option in audienceOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </a-radio-button>
          </a-radio-group>
        </a-form-item>

        <a-row v-if="assembleModal.data.audience_type === 'librarian'" :gutter="16">
          <a-col :span="14">
            <a-form-item label="图书馆类型">
              <a-checkbox-group v-model:value="assembleModal.data.library_types" :options="libraryTypeOptions" />
            </a-form-item>
          </a-col>
          <a-col :span="10">
            <a-form-item label="岗位类型">
              <a-radio-group v-model:value="assembleModal.data.job_type">
                <a-radio-button v-for="option in jobTypeOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </a-radio-button>
              </a-radio-group>
            </a-form-item>
          </a-col>
        </a-row>

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
          <a-col :span="12">
            <a-form-item label="目标难度">
              <a-space direction="vertical" style="width: 100%">
                <a-radio-group v-model:value="assembleModal.data.difficulty_preset" @change="handleDifficultyPresetChange">
                  <a-radio-button v-for="option in difficultyPresetOptions" :key="option.value" :value="option.value">
                    {{ option.label }}
                  </a-radio-button>
                </a-radio-group>
                <a-input-number
                  v-model:value="assembleModal.data.difficulty_target"
                  :min="1"
                  :max="5"
                  style="width: 100%"
                  addon-before="实际难度"
                  @change="handleDifficultyTargetChange"
                />
              </a-space>
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item label="难度容差">
              <a-input-number v-model:value="assembleModal.data.difficulty_tolerance" :min="0" :max="2" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item label="每题分值">
              <a-input-number v-model:value="assembleModal.data.score_per_question" :min="1" :max="50" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item label="试卷要求描述">
          <a-textarea
            v-model:value="assembleModal.data.requirements_prompt"
            :rows="3"
            :maxlength="500"
            placeholder="您可输入具体面向对象描述，试卷知识点侧重点比例等详细要求"
          />
        </a-form-item>

        <a-form-item :label="`知识维度占比（当前合计 ${dimensionWeightTotal()}%）`">
          <div class="dimension-weight-list">
            <div v-for="dimension in fiveDimensions" :key="dimension" class="dimension-weight-row">
              <span class="dimension-weight-label">{{ dimension }}</span>
              <a-input-number
                :value="assembleModal.data.dimension_weights[dimension]"
                :min="0"
                :max="100"
                addon-after="%"
                style="width: 140px"
                @change="handleDimensionWeightChange(dimension, $event)"
              />
            </div>
          </div>
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
          <a-descriptions-item v-if="formatAudienceSummary(detailDrawer.exam.params)" label="面向对象">
            {{ formatAudienceSummary(detailDrawer.exam.params) }}
          </a-descriptions-item>
          <a-descriptions-item v-if="formatLibrarySummary(detailDrawer.exam.params)" label="图书馆画像">
            {{ formatLibrarySummary(detailDrawer.exam.params) }}
          </a-descriptions-item>
          <a-descriptions-item v-if="formatDifficultySummary(detailDrawer.exam.params)" label="目标难度">
            {{ formatDifficultySummary(detailDrawer.exam.params) }}
          </a-descriptions-item>
          <a-descriptions-item v-if="detailDrawer.exam.params?.requirements_prompt" label="详细要求" :span="2">
            {{ detailDrawer.exam.params.requirements_prompt }}
          </a-descriptions-item>
          <a-descriptions-item v-if="formatDimensionWeightSummary(detailDrawer.exam.params)" label="维度占比" :span="2">
            {{ formatDimensionWeightSummary(detailDrawer.exam.params) }}
          </a-descriptions-item>
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
const fiveDimensions = ['AI基础知识', 'AI技术应用', 'AI伦理安全', 'AI批判思维', 'AI创新实践']
const audienceOptions = [
  { label: '不限', value: 'all' },
  { label: '图书馆员', value: 'librarian' },
  { label: '社科研究员/教师', value: 'researcher_teacher' },
  { label: '高校学生', value: 'college_student' },
]
const libraryTypeOptions = [
  { label: '公共', value: 'public' },
  { label: '高校', value: 'university' },
  { label: '研究', value: 'research' },
]
const jobTypeOptions = [
  { label: '综合', value: 'general' },
  { label: '技术', value: 'technical' },
  { label: '服务', value: 'service' },
]
const difficultyPresetOptions = [
  { label: '新手', value: 'newbie' },
  { label: '骨干', value: 'backbone' },
  { label: '专家', value: 'expert' },
  { label: '自定义', value: 'custom' },
]
const difficultyPresetValues: Record<string, number> = {
  newbie: 1,
  backbone: 3,
  expert: 5,
}

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

function createZeroDimensionWeights() {
  return Object.fromEntries(fiveDimensions.map(dimension => [dimension, 0])) as Record<string, number>
}

function createDefaultDimensionWeights() {
  return Object.fromEntries(fiveDimensions.map(dimension => [dimension, 20])) as Record<string, number>
}

function buildWeightsFromDimensions(dimensions: string[] = []) {
  const weights = createZeroDimensionWeights()
  const active = fiveDimensions.filter(dimension => dimensions.includes(dimension))
  if (active.length === 0) return createDefaultDimensionWeights()
  const base = Math.floor(100 / active.length)
  let remainder = 100 - (base * active.length)
  active.forEach((dimension) => {
    weights[dimension] = base + (remainder > 0 ? 1 : 0)
    if (remainder > 0) remainder -= 1
  })
  return weights
}

function normalizeDimensionWeights(raw: any) {
  if (!raw || typeof raw !== 'object') return createDefaultDimensionWeights()
  const normalized = createZeroDimensionWeights()
  let total = 0
  fiveDimensions.forEach((dimension) => {
    const value = Number(raw[dimension])
    const safeValue = Number.isFinite(value) ? Math.max(0, Math.min(100, Math.round(value))) : 0
    normalized[dimension] = safeValue
    total += safeValue
  })
  return total > 0 ? normalized : createDefaultDimensionWeights()
}

function createDefaultAssembleData() {
  return {
    audience_type: 'all',
    library_types: [] as string[],
    job_type: undefined as string | undefined,
    difficulty_preset: 'backbone',
    difficulty_target: 3,
    difficulty_tolerance: 1,
    score_per_question: 5,
    requirements_prompt: '',
    dimension_weights: createDefaultDimensionWeights(),
  }
}

// Assemble modal
const assembleModal = reactive({
  visible: false,
  loading: false,
  examId: null as string | null,
  data: createDefaultAssembleData(),
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

function dimensionWeightTotal() {
  return fiveDimensions.reduce((sum, dimension) => sum + Number(assembleModal.data.dimension_weights[dimension] || 0), 0)
}

function audienceLabel(value?: string) {
  return {
    all: '不限',
    librarian: '图书馆员',
    researcher_teacher: '社科研究员/教师',
    college_student: '高校学生',
  }[value || ''] || ''
}

function libraryTypeLabel(value?: string) {
  return {
    public: '公共',
    university: '高校',
    research: '研究',
  }[value || ''] || ''
}

function jobTypeLabel(value?: string) {
  return {
    general: '综合',
    technical: '技术',
    service: '服务',
  }[value || ''] || ''
}

function difficultyPresetLabel(value?: string) {
  return {
    newbie: '新手',
    backbone: '骨干',
    expert: '专家',
    custom: '自定义',
  }[value || ''] || ''
}

function formatAudienceSummary(params?: any) {
  return audienceLabel(params?.audience_type)
}

function formatLibrarySummary(params?: any) {
  if (params?.audience_type !== 'librarian') return ''
  const parts = []
  const libraryTypes = Array.isArray(params?.library_types) ? params.library_types.map((value: string) => libraryTypeLabel(value)).filter(Boolean) : []
  if (libraryTypes.length > 0) parts.push(`图书馆类型：${libraryTypes.join(' / ')}`)
  const jobLabel = jobTypeLabel(params?.job_type)
  if (jobLabel) parts.push(`岗位：${jobLabel}`)
  return parts.join('；')
}

function formatDifficultySummary(params?: any) {
  if (!params?.difficulty_target) return ''
  const presetLabel = difficultyPresetLabel(params?.difficulty_preset)
  return presetLabel ? `${presetLabel}（${params.difficulty_target}）` : String(params.difficulty_target)
}

function formatDimensionWeightSummary(params?: any) {
  const weights = params?.dimension_weights
  if (!weights || typeof weights !== 'object') return ''
  return fiveDimensions
    .map(dimension => `${dimension} ${Number(weights[dimension] || 0)}%`)
    .join('；')
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
  assembleModal.data = createDefaultAssembleData()
  const params = record.params || {}
  const storedTypeDistribution = params.type_distribution || {}
  typeDist.single_choice = Number(storedTypeDistribution.single_choice || 10)
  typeDist.multiple_choice = Number(storedTypeDistribution.multiple_choice || 0)
  typeDist.true_false = Number(storedTypeDistribution.true_false || 5)
  typeDist.fill_blank = Number(storedTypeDistribution.fill_blank || 0)
  typeDist.short_answer = Number(storedTypeDistribution.short_answer || 0)
  assembleModal.data.difficulty_target = Number(params.difficulty_target || 3)
  assembleModal.data.difficulty_tolerance = Number(params.difficulty_tolerance ?? 1)
  assembleModal.data.score_per_question = Number(params.score_per_question || 5)
  assembleModal.data.audience_type = params.audience_type || 'all'
  assembleModal.data.library_types = Array.isArray(params.library_types) ? [...params.library_types] : []
  assembleModal.data.job_type = params.job_type || undefined
  assembleModal.data.requirements_prompt = params.requirements_prompt || ''
  assembleModal.data.difficulty_preset = params.difficulty_preset || 'backbone'
  assembleModal.data.dimension_weights = params.dimension_weights
    ? normalizeDimensionWeights(params.dimension_weights)
    : buildWeightsFromDimensions(Array.isArray(params.dimensions) ? params.dimensions : [])
  handleAudienceTypeChange()
  handleDifficultyTargetChange(assembleModal.data.difficulty_target)
  assembleModal.visible = true
  // Fetch approved question count
  try {
    const data: any = await request.get('/questions', { params: { status: 'approved', skip: 0, limit: 1 } })
    approvedCount.value = data.total || 0
  } catch { approvedCount.value = 0 }
}

function handleAudienceTypeChange() {
  if (assembleModal.data.audience_type !== 'librarian') {
    assembleModal.data.library_types = []
    assembleModal.data.job_type = undefined
  }
}

function handleDifficultyPresetChange() {
  const preset = assembleModal.data.difficulty_preset
  if (preset && preset !== 'custom' && difficultyPresetValues[preset]) {
    assembleModal.data.difficulty_target = difficultyPresetValues[preset]
  }
}

function handleDifficultyTargetChange(value: number | string | null) {
  const parsed = Number(value)
  const safeValue = Number.isFinite(parsed) ? Math.max(1, Math.min(5, Math.round(parsed))) : 3
  assembleModal.data.difficulty_target = safeValue
  const matchedPreset = Object.entries(difficultyPresetValues).find(([, presetValue]) => presetValue === safeValue)?.[0]
  assembleModal.data.difficulty_preset = matchedPreset || 'custom'
}

function handleDimensionWeightChange(dimension: string, value: number | string | null) {
  const parsed = Number(value)
  assembleModal.data.dimension_weights[dimension] = Number.isFinite(parsed)
    ? Math.max(0, Math.min(100, Math.round(parsed)))
    : 0
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
  if (dimensionWeightTotal() !== 100) {
    message.warning('知识维度占比之和必须为 100%')
    return
  }
  if (assembleModal.data.audience_type === 'librarian' && !assembleModal.data.job_type) {
    message.warning('请选择岗位类型')
    return
  }
  assembleModal.loading = true
  try {
    const payload: any = {
      type_distribution: dist,
      difficulty_target: assembleModal.data.difficulty_target,
      difficulty_tolerance: assembleModal.data.difficulty_tolerance,
      score_per_question: assembleModal.data.score_per_question,
      difficulty_preset: assembleModal.data.difficulty_preset,
      audience_type: assembleModal.data.audience_type,
      dimension_weights: { ...assembleModal.data.dimension_weights },
    }
    if (assembleModal.data.requirements_prompt.trim()) {
      payload.requirements_prompt = assembleModal.data.requirements_prompt.trim()
    }
    if (assembleModal.data.audience_type === 'librarian') {
      if (assembleModal.data.library_types.length > 0) payload.library_types = assembleModal.data.library_types
      payload.job_type = assembleModal.data.job_type
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
.dimension-weight-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.dimension-weight-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 12px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  background: #fafafa;
}
.dimension-weight-label {
  color: #262626;
  font-weight: 500;
}
</style>
