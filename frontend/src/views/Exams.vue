<template>
  <div class="take-exam-page">
    <template v-if="randomTestResult">
      <div class="page-container">
        <div class="page-header">
          <h2>随机测试结果</h2>
        </div>
        <a-card class="card-container" :bordered="false">
          <a-result
            :status="randomTestResult.ratio >= 0.6 ? 'success' : 'warning'"
            :title="`得分：${randomTestResult.total_score} / ${randomTestResult.max_score}`"
          >
            <template #subTitle>
              <div class="result-subtitle">
                等级：<a-tag :color="randomTestResult.level === '优秀' ? 'green' : randomTestResult.level === '良好' ? 'blue' : randomTestResult.level === '合格' ? 'orange' : 'red'">{{ randomTestResult.level }}</a-tag>
                &nbsp;&nbsp;答对 {{ randomTestResult.correct_count }} / {{ randomTestResult.total_questions }} 题
                &nbsp;&nbsp;正确率 {{ (randomTestResult.ratio * 100).toFixed(0) }}%
              </div>
            </template>
            <template #extra>
              <a-button type="primary" :loading="cleanupLoading" @click="closeRandomTestResult">返回考试列表</a-button>
            </template>
          </a-result>
        </a-card>
      </div>
    </template>

    <template v-else-if="formalFlowState === 'processing'">
      <div class="page-container">
        <div class="page-header">
          <h2>正在生成诊断报告</h2>
        </div>
        <a-card class="card-container" :bordered="false">
          <div class="processing-hero">
            <div class="processing-hero-title">{{ processingContext?.examTitle || '考试' }}</div>
            <div class="processing-hero-subtitle">
              答卷已提交，系统正在评分并生成诊断报告。通常需要十几秒，请勿关闭页面。
            </div>
            <div class="processing-hero-meta">
              已答 {{ processingContext?.totalAnswered || 0 }}/{{ processingContext?.totalQuestions || 0 }} 题
            </div>
          </div>

          <a-steps direction="vertical" :current="processingStepIndex" class="processing-steps">
            <a-step title="答卷已提交" description="考试答案已保存，进入分析流程。" />
            <a-step title="正在评分" description="系统正在计算得分与题目表现。" />
            <a-step title="正在生成诊断报告" description="系统正在生成维度分析、错题总结与学习建议。" />
            <a-step title="诊断报告已就绪" description="处理完成后将自动展示报告。" />
          </a-steps>

          <a-alert
            type="info"
            show-icon
            :message="processingStatus.message || '系统正在处理中，请稍候。'"
            class="processing-alert"
          />
        </a-card>
      </div>
    </template>

    <template v-else-if="formalFlowState === 'processing_failed'">
      <div class="page-container">
        <div class="page-header">
          <h2>诊断报告生成失败</h2>
        </div>
        <a-card class="card-container" :bordered="false">
          <a-result
            status="error"
            title="本次分析暂时未完成"
            :sub-title="processingStatus.message || '生成诊断报告时发生错误，请重试。'"
          >
            <template #extra>
              <a-space wrap>
                <a-button type="primary" @click="retryProcessing">重试生成</a-button>
                <a-button @click="returnToScores">返回成绩页</a-button>
                <a-button @click="returnToExamList">返回考试列表</a-button>
              </a-space>
            </template>
          </a-result>
        </a-card>
      </div>
    </template>

    <template v-else-if="!session">
      <div class="page-container">
        <div class="page-header">
          <h2>考试管理</h2>
          <a-space>
            <a-button size="small" class="random-test-button" @click="showRandomTestModal">
              <ThunderboltOutlined /> 测试一下？
            </a-button>
          </a-space>
        </div>

        <a-card v-if="isManager" class="filter-card" :bordered="false">
          <a-row :gutter="16">
            <a-col :span="6">
              <a-input v-model:value="filters.keyword" placeholder="搜索考试名称" allow-clear @press-enter="fetchListData">
                <template #prefix><SearchOutlined /></template>
              </a-input>
            </a-col>
            <a-col :span="4">
              <a-select v-model:value="filters.status" placeholder="状态筛选" allow-clear class="full-width">
                <a-select-option value="published">已发布</a-select-option>
                <a-select-option value="closed">已关闭</a-select-option>
              </a-select>
            </a-col>
            <a-col :span="4">
              <a-button type="primary" @click="fetchListData">查询</a-button>
              <a-button class="reset-button" @click="resetFilters">重置</a-button>
            </a-col>
          </a-row>
        </a-card>

        <a-card v-if="isManager" class="card-container" :bordered="false">
          <a-table
            :columns="managerColumns"
            :data-source="managerExams"
            :loading="loadingExams"
            :pagination="pagination"
            row-key="id"
            @change="handleTableChange"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'status'">
                <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
              </template>
              <template v-else-if="column.key === 'time_limit'">
                {{ record.time_limit_minutes ? record.time_limit_minutes + ' 分钟' : '不限时' }}
              </template>
              <template v-else-if="column.key === 'created_at'">
                {{ formatDate(record.created_at) }}
              </template>
              <template v-else-if="column.key === 'actions'">
                <a-space>
                  <a @click="viewExam(record)">详情</a>
                  <a-popconfirm
                    v-if="record.status === 'published' || activeSessionByExamId[record.id]"
                    :title="activeSessionByExamId[record.id] ? '检测到未完成的考试会话，确定继续考试？' : '确定开始考试？开始后将计时。'"
                    @confirm="startExam(record.id)"
                  >
                    <a style="color: #1890ff">{{ activeSessionByExamId[record.id] ? '继续考试' : '开始考试' }}</a>
                  </a-popconfirm>
                  <a-popconfirm
                    v-if="record.status === 'published'"
                    title="确定关闭此考试？关闭后考生无法继续开始新考试。"
                    @confirm="closeExam(record)"
                  >
                    <a style="color: #faad14">关闭</a>
                  </a-popconfirm>
                  <a-popconfirm
                    v-if="record.status === 'closed'"
                    title="确定重新开放此考试？"
                    @confirm="reactivateExam(record)"
                  >
                    <a style="color: #52c41a">重新开放</a>
                  </a-popconfirm>
                  <a-popconfirm title="确定删除此考试？相关答题与成绩也会被删除。" @confirm="deleteExam(record)">
                    <a style="color: #ff4d4f">删除</a>
                  </a-popconfirm>
                </a-space>
              </template>
            </template>
          </a-table>
        </a-card>

        <a-card v-else class="card-container" :bordered="false">
          <a-list :loading="loadingExams" :data-source="displayedExams" :locale="{ emptyText: '暂无可用考试' }">
            <template #renderItem="{ item }">
              <a-list-item>
                <a-list-item-meta :title="item.title" :description="item.description || '暂无描述'" />
                <template #actions>
                  <a-tag v-if="activeSessionByExamId[item.id]" color="processing">进行中</a-tag>
                  <span v-if="item.time_limit_minutes">{{ item.time_limit_minutes }} 分钟</span>
                  <span v-if="item.total_score !== undefined && item.total_score !== null">总分 {{ item.total_score }}</span>
                  <a-popconfirm
                    :title="activeSessionByExamId[item.id] ? '检测到未完成的考试会话，确定继续考试？' : '确定开始考试？开始后将计时。'"
                    @confirm="startExam(item.id)"
                  >
                    <a-button type="primary" size="small">
                      {{ activeSessionByExamId[item.id] ? '继续考试' : '开始考试' }}
                    </a-button>
                  </a-popconfirm>
                </template>
              </a-list-item>
            </template>
          </a-list>
        </a-card>

        <a-modal
          v-model:open="randomTestModalVisible"
          title="随机测试设置"
          :confirm-loading="randomTestLoading"
          ok-text="开始测试"
          cancel-text="取消"
          @ok="startRandomTest"
        >
          <a-form layout="vertical" class="random-test-form">
            <a-form-item label="试题数量">
              <a-input-number v-model:value="randomTestForm.count" :min="5" :max="50" :step="5" class="full-width" />
            </a-form-item>
            <a-form-item label="试题难度">
              <a-radio-group v-model:value="randomTestForm.difficulty_mode" class="full-width">
                <div class="difficulty-options">
                  <a-radio value="easy" class="difficulty-option">
                    <span class="difficulty-title">自信心爆棚</span>
                    <span class="difficulty-desc">全是最简单的题目</span>
                  </a-radio>
                  <a-radio value="real" class="difficulty-option">
                    <span class="difficulty-title">真实水平</span>
                    <span class="difficulty-desc">难度均衡，适合检验真实水平</span>
                  </a-radio>
                  <a-radio value="hell" class="difficulty-option">
                    <span class="difficulty-title">挑战高难度</span>
                    <span class="difficulty-desc">高难度为主，适合进阶挑战</span>
                  </a-radio>
                </div>
              </a-radio-group>
            </a-form-item>
          </a-form>
          <div class="random-test-note">
            将随机抽取单选题、多选题、判断题（比例 6:2:2），总分 100 分，不限时。
          </div>
        </a-modal>

        <a-drawer
          v-model:open="detailDrawer.visible"
          :title="detailDrawer.exam?.title || '考试详情'"
          width="920"
        >
          <template v-if="detailDrawer.exam">
            <a-descriptions :column="2" bordered size="small">
              <a-descriptions-item label="状态">
                <a-tag :color="statusColor(detailDrawer.exam.status)">{{ statusLabel(detailDrawer.exam.status) }}</a-tag>
              </a-descriptions-item>
              <a-descriptions-item label="总分">{{ detailDrawer.exam.total_score }}</a-descriptions-item>
              <a-descriptions-item label="时长">
                {{ detailDrawer.exam.time_limit_minutes ? detailDrawer.exam.time_limit_minutes + ' 分钟' : '不限时' }}
              </a-descriptions-item>
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
                <template v-if="column.key === 'order'">{{ record.order_num || index + 1 }}</template>
                <template v-else-if="column.key === 'score'">{{ record.score }} 分</template>
                <template v-else-if="column.key === 'question_type'">{{ typeLabel(resolveQuestion(record)?.question_type) }}</template>
                <template v-else-if="column.key === 'dimension'">{{ resolveQuestion(record)?.dimension || '未分类' }}</template>
                <template v-else-if="column.key === 'difficulty'">{{ difficultyLabel(resolveQuestion(record)?.difficulty) }}</template>
                <template v-else-if="column.key === 'content'">
                  <div class="exam-question-content">
                    <div class="exam-question-stem">{{ resolveQuestion(record)?.stem || record.question_id || '无题干' }}</div>
                    <div v-if="hasQuestionOptions(resolveQuestion(record))" class="exam-question-options">
                      <div
                        v-for="option in normalizeQuestionOptions(resolveQuestion(record)?.options)"
                        :key="option.key"
                        class="exam-question-option"
                      >
                        <span class="exam-question-option-key">{{ option.key }}.</span>
                        <span>{{ option.value }}</span>
                      </div>
                    </div>
                  </div>
                </template>
              </template>
            </a-table>
          </template>
        </a-drawer>
      </div>
    </template>

    <template v-else>
      <div class="exam-container">
        <div class="exam-header">
          <div class="exam-title">{{ session.exam_title }}</div>
          <div class="exam-timer" :class="{ 'timer-warning': remainingSeconds !== null && remainingSeconds < 300 }">
            <ClockCircleOutlined />
            <span v-if="remainingSeconds !== null">{{ formatTime(remainingSeconds) }}</span>
            <span v-else>不限时</span>
          </div>
          <div class="exam-progress">
            {{ answeredCount }}/{{ questions.length }} 已答
          </div>
          <a-popconfirm title="确定提交考试？提交后不可修改。" @confirm="submitExam">
            <a-button type="primary" danger>交卷</a-button>
          </a-popconfirm>
        </div>

        <div class="exam-body">
          <div class="question-nav">
            <div class="nav-title">题目导航</div>
            <div class="nav-grid">
              <div
                v-for="(q, idx) in questions"
                :key="q.question_id"
                class="nav-item"
                :class="{
                  'nav-active': currentIndex === idx,
                  'nav-answered': answers[q.question_id],
                  'nav-marked': markedSet.has(q.question_id),
                }"
                @click="currentIndex = idx"
              >
                {{ idx + 1 }}
              </div>
            </div>
            <div class="nav-legend">
              <span><span class="dot dot-answered"></span>已答</span>
              <span><span class="dot dot-marked"></span>标记</span>
              <span><span class="dot dot-current"></span>当前</span>
            </div>
          </div>

          <div v-if="currentQuestion" class="question-content">
            <div class="question-header">
              <div class="question-header-main">
                <span class="question-num">第 {{ currentIndex + 1 }} 题</span>
                <a-tag>{{ typeLabel(currentQuestion.question_type) }}</a-tag>
                <a-tag color="blue">{{ currentQuestion.score }} 分</a-tag>
              </div>
              <div class="question-header-side">
                <a-tag v-if="currentQuestion.dimension" color="geekblue">{{ currentQuestion.dimension }}</a-tag>
                <a-button size="small" :type="markedSet.has(currentQuestion.question_id) ? 'primary' : 'default'" @click="toggleMark">
                  {{ markedSet.has(currentQuestion.question_id) ? '取消标记' : '标记' }}
                </a-button>
              </div>
            </div>

            <div class="question-stem">{{ currentQuestion.stem }}</div>

            <div v-if="currentQuestion.question_type === 'single_choice'" class="question-options">
              <a-radio-group v-model:value="answers[currentQuestion.question_id]" @change="saveAnswer">
                <div v-for="(val, key) in currentQuestion.options" :key="key" class="option-row">
                  <a-radio :value="key" class="option-item">
                    <span class="option-content">
                      <span class="option-label">{{ key }}.</span>
                      <span class="option-text">{{ val }}</span>
                    </span>
                  </a-radio>
                </div>
              </a-radio-group>
            </div>

            <div v-else-if="currentQuestion.question_type === 'multiple_choice'" class="question-options">
              <a-checkbox-group v-model:value="multiAnswers" @change="onMultiChange">
                <div v-for="(val, key) in currentQuestion.options" :key="key" class="option-row">
                  <a-checkbox :value="key" class="option-item">
                    <span class="option-content">
                      <span class="option-label">{{ key }}.</span>
                      <span class="option-text">{{ val }}</span>
                    </span>
                  </a-checkbox>
                </div>
              </a-checkbox-group>
            </div>

            <div v-else-if="currentQuestion.question_type === 'true_false'" class="question-options">
              <a-radio-group v-model:value="answers[currentQuestion.question_id]" @change="saveAnswer">
                <div class="option-row">
                  <a-radio value="T" class="option-item">
                    <span class="option-content">
                      <span class="option-label">T.</span>
                      <span class="option-text">正确</span>
                    </span>
                  </a-radio>
                </div>
                <div class="option-row">
                  <a-radio value="F" class="option-item">
                    <span class="option-content">
                      <span class="option-label">F.</span>
                      <span class="option-text">错误</span>
                    </span>
                  </a-radio>
                </div>
              </a-radio-group>
            </div>

            <div v-else class="question-options">
              <a-textarea
                v-model:value="answers[currentQuestion.question_id]"
                :rows="4"
                placeholder="请输入答案"
                @blur="saveAnswer"
              />
            </div>

            <div class="question-actions">
              <a-button :disabled="currentIndex === 0" @click="currentIndex--">上一题</a-button>
              <a-button type="primary" :disabled="currentIndex === questions.length - 1" @click="currentIndex++">下一题</a-button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ClockCircleOutlined, SearchOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import request from '@/utils/request'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const isManager = computed(() => {
  const role = userStore.userInfo?.role
  return role === 'admin' || role === 'organizer'
})

const loadingExams = ref(false)
const managerExams = ref<any[]>([])
const availableExams = ref<any[]>([])
const activeSessionByExamId = reactive<Record<string, string>>({})
const activeSessionMetaByExamId = reactive<Record<string, { id: string; exam_title: string; time_limit_minutes?: number | null }>>({})
const filters = reactive({ keyword: '', status: undefined as string | undefined })
const pagination = reactive({ current: 1, pageSize: 20, total: 0 })

const session = ref<any>(null)
const questions = ref<any[]>([])
const answers = reactive<Record<string, string>>({})
const markedSet = ref(new Set<string>())
const currentIndex = ref(0)
const remainingSeconds = ref<number | null>(null)
let timerInterval: ReturnType<typeof setInterval> | null = null

const randomTestModalVisible = ref(false)
const randomTestLoading = ref(false)
const randomTestForm = reactive({ count: 10, difficulty_mode: 'real' })
const isRandomTest = ref(false)
const randomTestResult = ref<any>(null)
const cleanupLoading = ref(false)

const formalFlowState = ref<'idle' | 'processing' | 'processing_failed'>('idle')
const processingContext = ref<any>(null)
const processingStatus = reactive({
  stage: 'submitted',
  score_id: '',
  diagnostic_ready: false,
  message: '',
})
let stopProcessingPolling = false

const detailDrawer = reactive({
  visible: false,
  exam: null as any,
  questions: [] as any[],
})

const managerColumns = [
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
  { title: '分值', key: 'score', width: 80 },
  { title: '题型', key: 'question_type', width: 100 },
  { title: '维度', key: 'dimension', width: 130, ellipsis: true },
  { title: '难度', key: 'difficulty', width: 90 },
  { title: '题目内容', key: 'content' },
]

const currentQuestion = computed(() => questions.value[currentIndex.value] || null)
const answeredCount = computed(() => questions.value.filter(q => answers[q.question_id]).length)
const displayedExams = computed(() => {
  const published = [...availableExams.value]
  const publishedIds = new Set(published.map(item => item.id))
  const resumedOnly = Object.entries(activeSessionMetaByExamId).flatMap(([examId, meta]) => {
    if (!meta || publishedIds.has(examId)) return []
    return [{
      id: examId,
      title: meta.exam_title,
      description: '未完成的考试会话',
      total_score: null,
      time_limit_minutes: meta.time_limit_minutes,
    }]
  })
  return [...resumedOnly, ...published]
})
const processingStepIndex = computed(() => {
  if (processingStatus.stage === 'completed') return 3
  if (processingStatus.stage === 'generating_diagnostic') return 2
  if (processingStatus.stage === 'scoring') return 1
  return 0
})

const multiAnswers = ref<string[]>([])

watch(currentIndex, () => {
  if (currentQuestion.value?.question_type === 'multiple_choice') {
    const current = answers[currentQuestion.value.question_id] || ''
    multiAnswers.value = current ? current.split('') : []
  }
})

function onMultiChange(vals: string[]) {
  if (!currentQuestion.value) return
  answers[currentQuestion.value.question_id] = vals.sort().join('')
  saveAnswer()
}

function statusColor(status: string) {
  return { published: 'green', closed: 'orange' }[status] || 'default'
}

function statusLabel(status: string) {
  return { published: '已发布', closed: '已关闭' }[status] || status
}

function typeLabel(type?: string) {
  return {
    single_choice: '单选题',
    multiple_choice: '多选题',
    true_false: '判断题',
    fill_blank: '填空题',
    short_answer: '简答题',
    essay: '论述题',
    sjt: '情境判断题',
  }[type || ''] || type || '-'
}

function difficultyLabel(value?: number) {
  return typeof value === 'number' ? `${value} / 5` : '-'
}

function formatDate(dateValue: string) {
  if (!dateValue) return ''
  return new Date(dateValue).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatTime(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${minutes.toString().padStart(2, '0')}:${rest.toString().padStart(2, '0')}`
}

function resolveQuestion(record: any) {
  return record?.question || record || null
}

function normalizeQuestionOptions(options?: Record<string, string> | null) {
  return Object.entries(options || {})
    .filter(([key, value]) => String(key).trim() && String(value).trim())
    .map(([key, value]) => ({ key, value }))
}

function hasQuestionOptions(question?: any) {
  return normalizeQuestionOptions(question?.options).length > 0
}

async function fetchListData() {
  loadingExams.value = true
  try {
    const examParams: any = isManager.value
      ? {
          skip: (pagination.current - 1) * pagination.pageSize,
          limit: pagination.pageSize,
          is_random_test: false,
        }
      : { status: 'published', skip: 0, limit: 50 }
    if (isManager.value && filters.keyword) examParams.keyword = filters.keyword
    if (isManager.value && filters.status) examParams.status = filters.status

    const [examData, sessionData]: [any, any] = await Promise.all([
      request.get('/exams', { params: examParams }),
      request.get('/sessions', { params: { skip: 0, limit: 100 } }),
    ])

    const nonRandom = (examData.items || []).filter((item: any) => !String(item.title || '').startsWith('随机测试'))
    if (isManager.value) {
      managerExams.value = nonRandom.filter((item: any) => item.status !== 'draft')
      pagination.total = examData.total || managerExams.value.length
    } else {
      availableExams.value = nonRandom.filter((item: any) => item.status === 'published')
    }

    Object.keys(activeSessionByExamId).forEach(key => delete activeSessionByExamId[key])
    Object.keys(activeSessionMetaByExamId).forEach(key => delete activeSessionMetaByExamId[key])
    for (const item of sessionData || []) {
      if (item?.status === 'in_progress' && item?.exam_id) {
        activeSessionByExamId[item.exam_id] = item.id
        activeSessionMetaByExamId[item.exam_id] = {
          id: item.id,
          exam_title: item.exam_title || '未完成考试',
          time_limit_minutes: item.time_limit_minutes,
        }
      }
    }
  } finally {
    loadingExams.value = false
  }
}

function handleTableChange(pag: any) {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  fetchListData()
}

function resetFilters() {
  filters.keyword = ''
  filters.status = undefined
  pagination.current = 1
  fetchListData()
}

function resetSessionState() {
  currentIndex.value = 0
  remainingSeconds.value = null
  if (timerInterval) {
    clearInterval(timerInterval)
    timerInterval = null
  }
  questions.value = []
  Object.keys(answers).forEach(key => delete answers[key])
  markedSet.value = new Set()
  multiAnswers.value = []
}

function resetFormalFlow() {
  formalFlowState.value = 'idle'
  processingContext.value = null
  processingStatus.stage = 'submitted'
  processingStatus.score_id = ''
  processingStatus.diagnostic_ready = false
  processingStatus.message = ''
}

function clearActiveSession(sheetId: string) {
  Object.keys(activeSessionByExamId).forEach(key => {
    if (activeSessionByExamId[key] === sheetId) delete activeSessionByExamId[key]
  })
  Object.keys(activeSessionMetaByExamId).forEach(key => {
    if (activeSessionMetaByExamId[key]?.id === sheetId) delete activeSessionMetaByExamId[key]
  })
}

function applyProcessingStatus(payload: any) {
  processingStatus.stage = payload?.stage || 'submitted'
  processingStatus.score_id = payload?.score_id || ''
  processingStatus.diagnostic_ready = Boolean(payload?.diagnostic_ready)
  processingStatus.message = payload?.message || ''
}

function wait(ms: number) {
  return new Promise(resolve => window.setTimeout(resolve, ms))
}

async function startExam(examId: string) {
  try {
    resetSessionState()
    const data: any = await request.post(`/sessions/start/${examId}`)
    session.value = data

    const sessionData: any = await request.get(`/sessions/${data.answer_sheet_id}`)
    questions.value = sessionData.questions || []
    if (sessionData.answers) {
      for (const [qid, ans] of Object.entries(sessionData.answers)) {
        answers[qid] = ans as string
      }
    }

    if (data.time_limit_minutes) {
      const elapsed = Math.floor((Date.now() - new Date(data.start_time).getTime()) / 1000)
      remainingSeconds.value = Math.max(0, data.time_limit_minutes * 60 - elapsed)
      startTimer()
    }
    message.success(data.resumed ? '已恢复未完成的考试' : '考试开始')
  } catch {
    // handled by request interceptor
  }
}

function startTimer() {
  timerInterval = setInterval(() => {
    if (remainingSeconds.value === null) return
    remainingSeconds.value -= 1
    if (remainingSeconds.value <= 0) {
      if (timerInterval) clearInterval(timerInterval)
      message.warning('时间到，自动交卷')
      submitExam()
    }
  }, 1000)
}

async function saveAnswer() {
  if (!currentQuestion.value || !session.value) return
  const content = answers[currentQuestion.value.question_id]
  if (!content) return
  try {
    await request.post(`/sessions/${session.value.answer_sheet_id}/answer`, {
      question_id: currentQuestion.value.question_id,
      answer_content: content,
    })
  } catch {
    // silent save
  }
}

async function toggleMark() {
  if (!currentQuestion.value || !session.value) return
  const questionId = currentQuestion.value.question_id
  const nextMarked = !markedSet.value.has(questionId)
  try {
    await request.post(`/sessions/${session.value.answer_sheet_id}/mark`, {
      question_id: questionId,
      is_marked: nextMarked,
    })
    if (nextMarked) markedSet.value.add(questionId)
    else markedSet.value.delete(questionId)
  } catch {
    // handled by request interceptor
  }
}

async function submitExam() {
  if (!session.value) return
  try {
    const sheetId = session.value.answer_sheet_id
    const examTitle = session.value.exam_title
    const data: any = await request.post(
      `/sessions/${sheetId}/submit`,
      undefined,
      isRandomTest.value ? undefined : { params: { auto_score: false } }
    )
    if (timerInterval) {
      clearInterval(timerInterval)
      timerInterval = null
    }

    if (isRandomTest.value) {
      try {
        const scoreData: any = await request.get(`/scores/sheet/${sheetId}`)
        const correctCount = (scoreData.details || []).filter((detail: any) => detail.is_correct).length
        const totalQuestions = (scoreData.details || []).length
        randomTestResult.value = {
          total_score: scoreData.total_score,
          max_score: scoreData.max_score,
          level: scoreData.level,
          ratio: scoreData.max_score > 0 ? scoreData.total_score / scoreData.max_score : 0,
          correct_count: correctCount,
          total_questions: totalQuestions,
          sheet_id: sheetId,
        }
      } catch {
        randomTestResult.value = {
          total_score: 0,
          max_score: 100,
          level: '-',
          ratio: 0,
          correct_count: 0,
          total_questions: data.total_questions,
          sheet_id: sheetId,
        }
      }
      session.value = null
      resetSessionState()
    } else {
      message.success(`交卷成功！已答 ${data.total_answered}/${data.total_questions} 题`)
      processingContext.value = {
        sheetId,
        examTitle,
        totalAnswered: data.total_answered,
        totalQuestions: data.total_questions,
      }
      applyProcessingStatus({ stage: 'submitted', message: '答卷已提交，处理中。' })
      formalFlowState.value = 'processing'
      session.value = null
      clearActiveSession(sheetId)
      resetSessionState()
      await startFormalProcessingFlow(sheetId)
    }
  } catch {
    // handled by request interceptor
  }
}

async function startFormalProcessingFlow(sheetId: string) {
  stopProcessingPolling = false
  formalFlowState.value = 'processing'
  try {
    const kickoff: any = await request.post(`/scores/process/${sheetId}`)
    applyProcessingStatus(kickoff)
    await pollFormalProcessingStatus(sheetId)
  } catch {
    formalFlowState.value = 'processing_failed'
    processingStatus.message = '处理流程启动失败，请重试。'
  }
}

async function pollFormalProcessingStatus(sheetId: string) {
  const startedAt = Date.now()
  while (!stopProcessingPolling && formalFlowState.value === 'processing') {
    const status: any = await request.get(`/scores/process/${sheetId}`)
    applyProcessingStatus(status)

    if (status.stage === 'completed' && status.score_id) {
      stopProcessingPolling = true
      router.replace({ name: 'ScoreDiagnostic', params: { scoreId: status.score_id } })
      return
    }
    if (status.stage === 'failed') {
      formalFlowState.value = 'processing_failed'
      return
    }

    const interval = Date.now() - startedAt < 20000 ? 2000 : 4000
    await wait(interval)
  }
}

async function retryProcessing() {
  if (!processingContext.value?.sheetId) return
  await startFormalProcessingFlow(processingContext.value.sheetId)
}

async function returnToExamList() {
  stopProcessingPolling = true
  resetFormalFlow()
  await fetchListData()
}

function returnToScores() {
  stopProcessingPolling = true
  resetFormalFlow()
  router.push({ name: 'Scores' })
}

function showRandomTestModal() {
  randomTestForm.count = 10
  randomTestForm.difficulty_mode = 'real'
  randomTestModalVisible.value = true
}

async function startRandomTest() {
  randomTestLoading.value = true
  try {
    resetSessionState()
    const data: any = await request.post('/sessions/random-test', {
      count: randomTestForm.count,
      difficulty_mode: randomTestForm.difficulty_mode,
    })
    randomTestModalVisible.value = false
    isRandomTest.value = true
    session.value = data

    const sessionData: any = await request.get(`/sessions/${data.answer_sheet_id}`)
    questions.value = sessionData.questions || []
    if (sessionData.answers) {
      for (const [qid, ans] of Object.entries(sessionData.answers)) {
        answers[qid] = ans as string
      }
    }
    message.success('随机测试开始')
  } catch {
    message.error('创建随机测试失败，请确认题库中有足够的已审核题目')
  } finally {
    randomTestLoading.value = false
  }
}

async function closeRandomTestResult() {
  cleanupLoading.value = true
  try {
    if (randomTestResult.value?.sheet_id) {
      await request.delete(`/sessions/random-test/${randomTestResult.value.sheet_id}`)
    }
  } catch {
    // cleanup is best-effort
  }
  cleanupLoading.value = false
  randomTestResult.value = null
  isRandomTest.value = false
  fetchListData()
}

async function viewExam(record: any) {
  try {
    const data: any = await request.get(`/exams/${record.id}`)
    detailDrawer.exam = data
    detailDrawer.questions = data.questions || []
    detailDrawer.visible = true
  } catch {
    // handled by request interceptor
  }
}

async function closeExam(record: any) {
  try {
    await request.post(`/exams/${record.id}/close`)
    message.success('已关闭')
    await fetchListData()
  } catch {
    // handled by request interceptor
  }
}

async function reactivateExam(record: any) {
  try {
    await request.post(`/exams/${record.id}/reactivate`)
    message.success('已重新开放')
    await fetchListData()
  } catch {
    // handled by request interceptor
  }
}

async function deleteExam(record: any) {
  try {
    await request.delete(`/exams/${record.id}`)
    message.success('已删除')
    await fetchListData()
  } catch {
    // handled by request interceptor
  }
}

onMounted(() => {
  fetchListData()
})

onUnmounted(() => {
  stopProcessingPolling = true
  if (timerInterval) clearInterval(timerInterval)
})
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-header h2 {
  margin: 0;
}
.result-subtitle {
  font-size: 15px;
  color: #666;
}
.filter-card {
  margin-bottom: 16px;
}
.full-width {
  width: 100%;
}
.reset-button {
  margin-left: 8px;
}
.random-test-button {
  background: #1f4e79;
  color: #fff;
  border-color: #1f4e79;
}
.random-test-form {
  margin-top: 16px;
}
.difficulty-options {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.difficulty-option {
  margin-right: 0;
}
.difficulty-title {
  font-weight: 500;
}
.difficulty-desc {
  color: #999;
  font-size: 12px;
  margin-left: 8px;
}
.random-test-note {
  padding: 12px;
  background: #f5f5f5;
  border-radius: 6px;
  font-size: 13px;
  color: #666;
}
.processing-hero {
  padding: 24px;
  border-radius: 8px;
  background: linear-gradient(135deg, #f5f9ff 0%, #eef5fb 100%);
  margin-bottom: 20px;
}
.processing-hero-title {
  font-size: 22px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #1f4e79;
}
.processing-hero-subtitle {
  color: #4f5b67;
  line-height: 1.8;
  margin-bottom: 8px;
}
.processing-hero-meta {
  color: #7a8590;
  font-size: 13px;
}
.processing-steps {
  margin-top: 8px;
}
.processing-alert {
  margin-top: 16px;
}
.exam-container {
  height: calc(100vh - 112px);
  display: flex;
  flex-direction: column;
}
.exam-header {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 12px 24px;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}
.exam-title {
  font-size: 18px;
  font-weight: 600;
  flex: 1;
}
.exam-timer {
  font-size: 16px;
  font-weight: 500;
  color: #1f4e79;
  display: flex;
  align-items: center;
  gap: 6px;
}
.timer-warning {
  color: #ff4d4f;
  animation: blink 1s infinite;
}
@keyframes blink {
  50% { opacity: 0.5; }
}
.exam-progress {
  color: #666;
}
.exam-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}
.question-nav {
  width: 200px;
  background: #fafafa;
  border-right: 1px solid #f0f0f0;
  padding: 16px;
  overflow-y: auto;
  flex-shrink: 0;
}
.nav-title {
  font-weight: 600;
  margin-bottom: 12px;
}
.nav-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
}
.nav-item {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  background: #fff;
  border: 1px solid #d9d9d9;
  transition: all 0.2s;
}
.nav-item:hover {
  border-color: #1f4e79;
}
.nav-active {
  border-color: #1f4e79;
  background: #1f4e79;
  color: #fff;
}
.nav-answered {
  background: #e6f7ff;
  border-color: #91d5ff;
}
.nav-marked {
  border-color: #faad14;
  box-shadow: 0 0 0 2px rgba(250, 173, 20, 0.3);
}
.nav-legend {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #999;
}
.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 4px;
}
.dot-answered {
  background: #e6f7ff;
  border: 1px solid #91d5ff;
}
.dot-marked {
  border: 1px solid #faad14;
  background: transparent;
}
.dot-current {
  background: #1f4e79;
}
.question-content {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
}
.question-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.question-header-main,
.question-header-side {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.question-header-side {
  justify-content: flex-end;
}
.question-num {
  font-size: 16px;
  font-weight: 600;
}
.question-stem {
  font-size: 15px;
  line-height: 1.8;
  margin-bottom: 20px;
  white-space: pre-wrap;
}
.question-options {
  margin-bottom: 24px;
}
.question-options :deep(.ant-radio-group),
.question-options :deep(.ant-checkbox-group) {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.option-row {
  width: 100%;
}
.question-options :deep(.ant-radio-wrapper),
.question-options :deep(.ant-checkbox-wrapper) {
  width: 100%;
  display: flex;
  align-items: flex-start;
  margin-inline-start: 0;
  white-space: normal;
}
.question-options :deep(.ant-radio),
.question-options :deep(.ant-checkbox) {
  margin-top: 0.35em;
}
.question-options :deep(.ant-radio + span),
.question-options :deep(.ant-checkbox + span) {
  flex: 1;
  min-width: 0;
  padding-inline-start: 8px;
  white-space: normal;
}
.option-item {
  font-size: 14px;
  line-height: 1.6;
}
.option-content {
  display: flex;
  align-items: flex-start;
  gap: 4px;
}
.option-label {
  flex: 0 0 auto;
}
.option-text {
  flex: 1;
  min-width: 0;
  white-space: normal;
  word-break: break-word;
}
.question-actions {
  display: flex;
  gap: 12px;
  margin-top: 24px;
}
.exam-question-content {
  line-height: 1.6;
}
.exam-question-stem {
  white-space: pre-wrap;
}
.exam-question-options {
  margin-top: 8px;
  color: #555;
}
.exam-question-option {
  display: flex;
  gap: 4px;
}
.exam-question-option-key {
  font-weight: 600;
}
</style>
