<template>
  <div class="take-exam-page">
    <!-- Random Test Result (shown after submission) -->
    <template v-if="randomTestResult">
      <div class="page-container">
        <div class="page-header">
          <h2>随机测试��果</h2>
        </div>
        <a-card class="card-container" :bordered="false">
          <a-result
            :status="randomTestResult.ratio >= 0.6 ? 'success' : 'warning'"
            :title="`得分：${randomTestResult.total_score} / ${randomTestResult.max_score}`"
          >
            <template #subTitle>
              <div style="font-size: 15px; color: #666">
                等级：<a-tag :color="randomTestResult.level === '优秀' ? 'green' : randomTestResult.level === '良好' ? 'blue' : randomTestResult.level === '合格' ? 'orange' : 'red'">{{ randomTestResult.level }}</a-tag>
                &nbsp;&nbsp;答对 {{ randomTestResult.correct_count }} / {{ randomTestResult.total_questions }} 题
                &nbsp;&nbsp;正确率 {{ (randomTestResult.ratio * 100).toFixed(0) }}%
              </div>
            </template>
            <template #extra>
              <a-button type="primary" @click="closeRandomTestResult" :loading="cleanupLoading">返回考试列表</a-button>
            </template>
          </a-result>
        </a-card>
      </div>
    </template>

    <!-- Exam In Progress (fullscreen exam-taking UI) -->
    <template v-else-if="session">
      <div class="exam-container">
        <div class="exam-header">
          <div class="exam-title">{{ session.exam_title }}</div>
          <div class="exam-timer" :class="{ 'timer-warning': remainingSeconds !== null && remainingSeconds < 300 }">
            <ClockCircleOutlined />
            <span v-if="remainingSeconds !== null">{{ formatTime(remainingSeconds) }}</span>
            <span v-else>不限时</span>
          </div>
          <div class="exam-progress">
            {{ answeredCount }}/{{ examQuestions.length }} 已答
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
                v-for="(q, idx) in examQuestions"
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

          <div class="question-content" v-if="currentQuestion">
            <div class="question-header-bar">
              <span class="question-num">第 {{ currentIndex + 1 }} 题</span>
              <a-tag>{{ typeLabel(currentQuestion.question_type) }}</a-tag>
              <a-tag color="blue">{{ currentQuestion.score }} 分</a-tag>
              <a-button size="small" :type="markedSet.has(currentQuestion.question_id) ? 'primary' : 'default'" @click="toggleMark">
                {{ markedSet.has(currentQuestion.question_id) ? '取消标记' : '标记' }}
              </a-button>
            </div>

            <div class="question-stem">{{ currentQuestion.stem }}</div>

            <div v-if="currentQuestion.question_type === 'single_choice'" class="question-options">
              <a-radio-group v-model:value="answers[currentQuestion.question_id]" @change="saveAnswer">
                <a-radio v-for="(val, key) in currentQuestion.options" :key="key" :value="key" class="option-item">
                  {{ key }}. {{ val }}
                </a-radio>
              </a-radio-group>
            </div>

            <div v-else-if="currentQuestion.question_type === 'multiple_choice'" class="question-options">
              <a-checkbox-group v-model:value="multiAnswers" @change="onMultiChange">
                <a-checkbox v-for="(val, key) in currentQuestion.options" :key="key" :value="key" class="option-item">
                  {{ key }}. {{ val }}
                </a-checkbox>
              </a-checkbox-group>
            </div>

            <div v-else-if="currentQuestion.question_type === 'true_false'" class="question-options">
              <a-radio-group v-model:value="answers[currentQuestion.question_id]" @change="saveAnswer">
                <a-radio value="T" class="option-item">T. 正确</a-radio>
                <a-radio value="F" class="option-item">F. 错误</a-radio>
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
              <a-button type="primary" :disabled="currentIndex === examQuestions.length - 1" @click="currentIndex++">下一题</a-button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Main Page: Published Exam List -->
    <template v-else>
      <div class="page-container">
        <div class="page-header">
          <h2>考试管理</h2>
          <a-space>
            <a-button size="small" style="background: #1f4e79; color: #fff; border-color: #1f4e79" @click="showRandomTestModal">
              <ThunderboltOutlined /> 测试一下？
            </a-button>
          </a-space>
        </div>

        <!-- Filter Bar (manager only) -->
        <a-card v-if="isManager" class="filter-card" :bordered="false">
          <a-row :gutter="16">
            <a-col :span="6">
              <a-input v-model:value="filters.keyword" placeholder="搜索考试名称" allow-clear @press-enter="fetchExams">
                <template #prefix><SearchOutlined /></template>
              </a-input>
            </a-col>
            <a-col :span="4">
              <a-button type="primary" @click="fetchExams">查询</a-button>
              <a-button style="margin-left: 8px" @click="resetFilters">重置</a-button>
            </a-col>
          </a-row>
        </a-card>

        <!-- Exam Table (管理员/组织者看到完整表格) -->
        <a-card v-if="isManager" class="card-container" :bordered="false">
          <a-table
            :columns="columns"
            :data-source="exams"
            :loading="loading"
            :pagination="pagination"
            row-key="id"
            @change="handleTableChange"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'time_limit'">
                {{ record.time_limit_minutes ? record.time_limit_minutes + ' 分钟' : '不限时' }}
              </template>
              <template v-if="column.key === 'created_at'">
                {{ formatDate(record.created_at) }}
              </template>
              <template v-if="column.key === 'actions'">
                <a-space>
                  <a @click="viewExam(record)">详情</a>
                  <a-popconfirm title="确定开始考试？开始后将计时。" @confirm="startExam(record.id)" v-if="record.status === 'published'">
                    <a style="color: #1890ff">开始考试</a>
                  </a-popconfirm>
                  <a @click="showEditModal(record)" v-if="record.status === 'published'">编辑</a>
                  <a-popconfirm title="确定关闭此考试？关闭后考生无法继续作答。" @confirm="closeExam(record)" v-if="record.status === 'published'">
                    <a style="color: #faad14">关闭</a>
                  </a-popconfirm>
                  <a-popconfirm title="确定重新开放此考试？" @confirm="reactivateExam(record)" v-if="record.status === 'closed'">
                    <a style="color: #52c41a">重���开放</a>
                  </a-popconfirm>
                  <a-popconfirm title="确定删除此考试？" @confirm="deleteExam(record)" v-if="record.status === 'closed' || record.status === 'published' || record.status === 'draft'">
                    <a style="color: #ff4d4f">删除</a>
                  </a-popconfirm>
                </a-space>
              </template>
            </template>
          </a-table>
        </a-card>

        <!-- 考生视图：简洁的考试列表 -->
        <a-card v-else class="card-container" :bordered="false">
          <a-list :loading="loading" :data-source="availableExams" :locale="{ emptyText: '暂无可用考试' }">
            <template #renderItem="{ item }">
              <a-list-item>
                <a-list-item-meta :title="item.title" :description="item.description || '暂无描述'" />
                <template #actions>
                  <span v-if="item.time_limit_minutes">{{ item.time_limit_minutes }} 分钟</span>
                  <span>总分 {{ item.total_score }}</span>
                  <a-popconfirm title="确定开始考试？开始后将计时。" @confirm="startExam(item.id)">
                    <a-button type="primary" size="small">开始���试</a-button>
                  </a-popconfirm>
                </template>
              </a-list-item>
            </template>
          </a-list>
        </a-card>

        <!-- Edit Exam Modal (仅修改考试属性，不动试题) -->
        <a-modal
          v-model:open="editModal.visible"
          title="编辑考试信息"
          @ok="handleEdit"
          :confirm-loading="editModal.loading"
        >
          <a-form :model="editModal.data" layout="vertical">
            <a-form-item label="考试名称" required>
              <a-input v-model:value="editModal.data.title" placeholder="请输入考试名称" />
            </a-form-item>
            <a-form-item label="考试描述">
              <a-textarea v-model:value="editModal.data.description" placeholder="请���入考试描述" :rows="3" />
            </a-form-item>
            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item label="考试时长（分钟）">
                  <a-input-number v-model:value="editModal.data.time_limit_minutes" :min="1" :max="300" placeholder="不限时" style="width: 100%" />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="总分">
                  <a-input-number v-model:value="editModal.data.total_score" :min="1" :max="1000" style="width: 100%" />
                </a-form-item>
              </a-col>
            </a-row>
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

        <!-- Random Test Modal -->
        <a-modal
          v-model:open="randomTestModalVisible"
          title="随机测试设置"
          :confirm-loading="randomTestLoading"
          @ok="startRandomTest"
          ok-text="开始测试"
          cancel-text="取消"
        >
          <a-form layout="vertical" style="margin-top: 16px">
            <a-form-item label="试题数量">
              <a-input-number v-model:value="randomTestForm.count" :min="5" :max="50" :step="5" style="width: 100%" />
            </a-form-item>
            <a-form-item label="试题难度">
              <a-radio-group v-model:value="randomTestForm.difficulty_mode" style="width: 100%">
                <div style="display: flex; flex-direction: column; gap: 12px">
                  <a-radio value="easy" style="margin-right: 0">
                    <span style="font-weight: 500">😎 自信心爆棚</span>
                    <span style="color: #999; font-size: 12px; margin-left: 8px">全是最简单的题目</span>
                  </a-radio>
                  <a-radio value="real" style="margin-right: 0">
                    <span style="font-weight: 500">📊 真实水平</span>
                    <span style="color: #999; font-size: 12px; margin-left: 8px">难度均衡，适合检验真实水平</span>
                  </a-radio>
                  <a-radio value="hell" style="margin-right: 0">
                    <span style="font-weight: 500">🔥 挑战地狱难度</span>
                    <span style="color: #999; font-size: 12px; margin-left: 8px">高难度为主，勇者的选择</span>
                  </a-radio>
                </div>
              </a-radio-group>
            </a-form-item>
          </a-form>
          <div style="padding: 12px; background: #f5f5f5; border-radius: 6px; font-size: 13px; color: #666">
            将随机抽取单选题、多选题、判断题（比例 6:2:2），总分 100 分，不限时。
          </div>
        </a-modal>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { SearchOutlined, ClockCircleOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import { useUserStore } from '@/stores/user'
import request from '@/utils/request'

const router = useRouter()
const userStore = useUserStore()

const isManager = computed(() => {
  const role = userStore.userInfo?.role
  return role === 'admin' || role === 'organizer'
})

// ── Exam List ─────────────────��───────────────────────────────────────────

const loading = ref(false)
const exams = ref<any[]>([])
const availableExams = ref<any[]>([])  // 考生用：仅 published
const filters = reactive({ keyword: '', status: undefined as string | undefined })
const pagination = reactive({ current: 1, pageSize: 20, total: 0 })

const columns = [
  { title: '考试名称', dataIndex: 'title', key: 'title', ellipsis: true },
  { title: '总分', dataIndex: 'total_score', key: 'total_score', width: 80 },
  { title: '时长', key: 'time_limit', width: 100 },
  { title: '使用次数', dataIndex: 'usage_count', key: 'usage_count', width: 90 },
  { title: '创建时间', key: 'created_at', width: 160 },
  { title: '操作', key: 'actions', width: 280, fixed: 'right' },
]

const questionColumns = [
  { title: '序号', key: 'order', width: 60 },
  { title: '题目ID', dataIndex: 'question_id', key: 'question_id', ellipsis: true },
  { title: '分值', key: 'score', width: 80 },
]

// Edit modal
const editModal = reactive({
  visible: false,
  loading: false,
  editId: null as string | null,
  data: { title: '', description: '', time_limit_minutes: null as number | null, total_score: 100 },
})

// Detail drawer
const detailDrawer = reactive({
  visible: false,
  exam: null as any,
  questions: [] as any[],
})

function statusColor(s: string) {
  return { published: 'green', closed: 'orange' }[s] || 'default'
}
function statusLabel(s: string) {
  return { published: '已发布', closed: '已关闭' }[s] || s
}
function formatDate(d: string) {
  if (!d) return ''
  return new Date(d).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function fetchExams() {
  loading.value = true
  try {
    if (isManager.value) {
      // 管理员：看所有已发布和已关闭的考试（排除随机测试和草稿）
      const params: any = {
        skip: (pagination.current - 1) * pagination.pageSize,
        limit: pagination.pageSize,
        is_random_test: false,
      }
      if (filters.keyword) params.keyword = filters.keyword
      if (filters.status) params.status = filters.status
      const data: any = await request.get('/exams', { params })
      exams.value = (data.items || []).filter((e: any) => e.status !== 'draft')
      pagination.total = data.total || 0
    } else {
      // 考生：只看已发布的考试
      const data: any = await request.get('/exams', { params: { status: 'published', skip: 0, limit: 50 } })
      availableExams.value = (data.items || []).filter((e: any) => !e.title.startsWith('随机测试'))
    }
  } catch { /* handled by interceptor */ } finally {
    loading.value = false
  }
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

// Edit exam info
function showEditModal(record: any) {
  editModal.editId = record.id
  editModal.data = {
    title: record.title,
    description: record.description || '',
    time_limit_minutes: record.time_limit_minutes,
    total_score: record.total_score,
  }
  editModal.visible = true
}

async function handleEdit() {
  if (!editModal.data.title) {
    message.warning('请��入考试���称')
    return
  }
  editModal.loading = true
  try {
    const payload: any = { ...editModal.data }
    if (!payload.time_limit_minutes) delete payload.time_limit_minutes
    await request.put(`/exams/${editModal.editId}`, payload)
    message.success('更新成功')
    editModal.visible = false
    fetchExams()
  } catch { /* handled */ } finally {
    editModal.loading = false
  }
}

// View exam detail
async function viewExam(record: any) {
  try {
    const data: any = await request.get(`/exams/${record.id}`)
    detailDrawer.exam = data
    detailDrawer.questions = data.questions || []
    detailDrawer.visible = true
  } catch { /* handled */ }
}

// Close exam
async function closeExam(record: any) {
  try {
    await request.post(`/exams/${record.id}/close`)
    message.success('已关闭')
    fetchExams()
  } catch { /* handled */ }
}

// Reactivate exam
async function reactivateExam(record: any) {
  try {
    await request.post(`/exams/${record.id}/reactivate`)
    message.success('已重新开放')
    fetchExams()
  } catch { /* handled */ }
}

// Delete exam
async function deleteExam(record: any) {
  try {
    await request.delete(`/exams/${record.id}`)
    message.success('已删除')
    fetchExams()
  } catch { /* handled */ }
}

// ── Exam-Taking ──────────────��────────────────────────────────────────────

const session = ref<any>(null)
const examQuestions = ref<any[]>([])
const answers = reactive<Record<string, string>>({})
const markedSet = ref(new Set<string>())
const currentIndex = ref(0)
const remainingSeconds = ref<number | null>(null)
let timerInterval: any = null

// Random test state
const randomTestModalVisible = ref(false)
const randomTestLoading = ref(false)
const randomTestForm = reactive({ count: 10, difficulty_mode: 'real' })
const isRandomTest = ref(false)
const randomTestResult = ref<any>(null)
const cleanupLoading = ref(false)

const currentQuestion = computed(() => examQuestions.value[currentIndex.value] || null)
const answeredCount = computed(() => examQuestions.value.filter(q => answers[q.question_id]).length)

const multiAnswers = ref<string[]>([])

watch(currentIndex, () => {
  if (currentQuestion.value?.question_type === 'multiple_choice') {
    const current = answers[currentQuestion.value.question_id] || ''
    multiAnswers.value = current ? current.split('') : []
  }
})

function onMultiChange(vals: string[]) {
  if (currentQuestion.value) {
    answers[currentQuestion.value.question_id] = vals.sort().join('')
    saveAnswer()
  }
}

function typeLabel(t: string) {
  return { single_choice: '单选题', multiple_choice: '多���题', true_false: '判断题', fill_blank: '填空题', short_answer: '简答题' }[t] || t
}

function formatTime(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

async function startExam(examId: string) {
  try {
    const data: any = await request.post(`/sessions/start/${examId}`)
    session.value = data

    const sessionData: any = await request.get(`/sessions/${data.answer_sheet_id}`)
    examQuestions.value = sessionData.questions || []
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
    currentIndex.value = 0
    message.success('考试开始')
  } catch { /* handled */ }
}

function startTimer() {
  timerInterval = setInterval(() => {
    if (remainingSeconds.value !== null) {
      remainingSeconds.value--
      if (remainingSeconds.value <= 0) {
        clearInterval(timerInterval)
        message.warning('时间到，自动交卷')
        submitExam()
      }
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
  } catch { /* silent save */ }
}

async function toggleMark() {
  if (!currentQuestion.value || !session.value) return
  const qid = currentQuestion.value.question_id
  const newMark = !markedSet.value.has(qid)
  try {
    await request.post(`/sessions/${session.value.answer_sheet_id}/mark`, {
      question_id: qid,
      is_marked: newMark,
    })
    if (newMark) markedSet.value.add(qid)
    else markedSet.value.delete(qid)
  } catch { /* handled */ }
}

async function submitExam() {
  if (!session.value) return
  try {
    const sheetId = session.value.answer_sheet_id
    const data: any = await request.post(`/sessions/${sheetId}/submit`)
    clearInterval(timerInterval)

    if (isRandomTest.value) {
      try {
        const scoreData: any = await request.get(`/scores/sheet/${sheetId}`)
        const correctCount = (scoreData.details || []).filter((d: any) => d.is_correct).length
        const totalQ = (scoreData.details || []).length
        randomTestResult.value = {
          total_score: scoreData.total_score,
          max_score: scoreData.max_score,
          level: scoreData.level,
          ratio: scoreData.max_score > 0 ? scoreData.total_score / scoreData.max_score : 0,
          correct_count: correctCount,
          total_questions: totalQ,
          sheet_id: sheetId,
        }
      } catch {
        randomTestResult.value = {
          total_score: 0, max_score: 100, level: '\u2014',
          ratio: 0, correct_count: 0,
          total_questions: data.total_questions,
          sheet_id: sheetId,
        }
      }
      session.value = null
      examQuestions.value = []
      Object.keys(answers).forEach(k => delete answers[k])
    } else {
      message.success(`交卷成功！已答 ${data.total_answered}/${data.total_questions} 题`)
      session.value = null
      examQuestions.value = []
      Object.keys(answers).forEach(k => delete answers[k])
      router.push({ name: 'Scores' })
    }
  } catch { /* handled */ }
}

function showRandomTestModal() {
  randomTestForm.count = 10
  randomTestForm.difficulty_mode = 'real'
  randomTestModalVisible.value = true
}

async function startRandomTest() {
  randomTestLoading.value = true
  try {
    const data: any = await request.post('/sessions/random-test', {
      count: randomTestForm.count,
      difficulty_mode: randomTestForm.difficulty_mode,
    })
    randomTestModalVisible.value = false
    isRandomTest.value = true
    session.value = data

    const sessionData: any = await request.get(`/sessions/${data.answer_sheet_id}`)
    examQuestions.value = sessionData.questions || []
    if (sessionData.answers) {
      for (const [qid, ans] of Object.entries(sessionData.answers)) {
        answers[qid] = ans as string
      }
    }
    currentIndex.value = 0
    message.success('随机测试开始')
  } catch {
    message.error('创建随机测试失���，请确认题库中有足够的已审核题目')
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
  } catch { /* silent cleanup */ }
  cleanupLoading.value = false
  randomTestResult.value = null
  isRandomTest.value = false
  fetchExams()
}

// ── Init ──────────────────────────────────────��───────────────────────────

onMounted(() => { fetchExams() })
onUnmounted(() => { if (timerInterval) clearInterval(timerInterval) })
</script>

<style scoped>
.filter-card { margin-bottom: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-header h2 { margin: 0; }
.exam-container { height: calc(100vh - 112px); display: flex; flex-direction: column; }
.exam-header {
  display: flex; align-items: center; gap: 24px; padding: 12px 24px;
  background: #fff; border-bottom: 1px solid #f0f0f0; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.exam-title { font-size: 18px; font-weight: 600; flex: 1; }
.exam-timer { font-size: 16px; font-weight: 500; color: #1F4E79; display: flex; align-items: center; gap: 6px; }
.timer-warning { color: #ff4d4f; animation: blink 1s infinite; }
@keyframes blink { 50% { opacity: 0.5; } }
.exam-progress { color: #666; }
.exam-body { flex: 1; display: flex; overflow: hidden; }
.question-nav {
  width: 200px; background: #fafafa; border-right: 1px solid #f0f0f0;
  padding: 16px; overflow-y: auto; flex-shrink: 0;
}
.nav-title { font-weight: 600; margin-bottom: 12px; }
.nav-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
.nav-item {
  width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;
  border-radius: 4px; cursor: pointer; font-size: 12px;
  background: #fff; border: 1px solid #d9d9d9; transition: all 0.2s;
}
.nav-item:hover { border-color: #1F4E79; }
.nav-active { border-color: #1F4E79; background: #1F4E79; color: #fff; }
.nav-answered { background: #e6f7ff; border-color: #91d5ff; }
.nav-marked { border-color: #faad14; box-shadow: 0 0 0 2px rgba(250,173,20,0.3); }
.nav-legend { margin-top: 16px; display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #999; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; }
.dot-answered { background: #e6f7ff; border: 1px solid #91d5ff; }
.dot-marked { border: 1px solid #faad14; background: transparent; }
.dot-current { background: #1F4E79; }
.question-content { flex: 1; padding: 24px; overflow-y: auto; }
.question-header-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
.question-num { font-size: 16px; font-weight: 600; }
.question-stem { font-size: 15px; line-height: 1.8; margin-bottom: 20px; white-space: pre-wrap; }
.question-options { margin-bottom: 24px; }
.option-item { display: block; margin-bottom: 12px; font-size: 14px; line-height: 1.6; }
.question-actions { display: flex; gap: 12px; margin-top: 24px; }
</style>
