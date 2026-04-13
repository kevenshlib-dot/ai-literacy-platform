<template>
  <div class="take-exam-page">
    <!-- Random Test Result (shown after submission) -->
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

    <!-- Exam List (before starting) -->
    <template v-else-if="!session">
      <div class="page-container">
        <div class="page-header">
          <h2>在线考试</h2>
          <a-button size="small" style="background: #1f4e79; color: #fff; border-color: #1f4e79" @click="showRandomTestModal">
            <ThunderboltOutlined /> 测试一下？
          </a-button>
        </div>

        <!-- Resume in-progress exam banner -->
        <a-alert
          v-if="inProgressSession"
          type="info"
          show-icon
          style="margin-bottom: 16px"
          :message="`您有一场正在进行的考试：「${inProgressSession.exam_title}」`"
        >
          <template #action>
            <a-button type="primary" size="small" :loading="resumingExam" @click="resumeExam(inProgressSession)">
              继续考试
            </a-button>
          </template>
        </a-alert>

        <!-- Published Exams -->
        <a-card class="card-container" :bordered="false">
          <a-list :loading="loadingExams" :data-source="availableExams" :locale="{ emptyText: '暂无可用考试' }">
            <template #renderItem="{ item }">
              <a-list-item>
                <a-list-item-meta :title="item.title" :description="item.description || '暂无描述'" />
                <template #actions>
                  <span v-if="item.time_limit_minutes">{{ item.time_limit_minutes }} 分钟</span>
                  <span>总分 {{ item.total_score }}</span>
                  <a-popconfirm title="确定开始考试？开始后将计时。" @confirm="startExam(item.id)">
                    <a-button type="primary" size="small">开始考试</a-button>
                  </a-popconfirm>
                </template>
              </a-list-item>
            </template>
          </a-list>
        </a-card>

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

    <!-- Exam In Progress -->
    <template v-else>
      <div class="exam-container">
        <!-- Header -->
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
          <!-- Question Navigation -->
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

          <!-- Question Content -->
          <div class="question-content" v-if="currentQuestion">
            <div class="question-header">
              <span class="question-num">第 {{ currentIndex + 1 }} 题</span>
              <a-tag>{{ typeLabel(currentQuestion.question_type) }}</a-tag>
              <a-tag color="blue">{{ currentQuestion.score }} 分</a-tag>
              <a-button size="small" :type="markedSet.has(currentQuestion.question_id) ? 'primary' : 'default'" @click="toggleMark">
                {{ markedSet.has(currentQuestion.question_id) ? '取消标记' : '标记' }}
              </a-button>
            </div>

            <div class="question-stem">{{ currentQuestion.stem }}</div>

            <!-- Choice Questions -->
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

            <!-- Navigation Buttons -->
            <div class="question-actions">
              <a-button :disabled="currentIndex === 0" @click="currentIndex--">上一题</a-button>
              <a-button v-if="currentIndex < questions.length - 1" type="primary" @click="currentIndex++">下一题</a-button>
              <a-popconfirm v-else title="确定提交考试？提交后不可修改。" @confirm="submitExam">
                <a-button type="primary" danger>交卷</a-button>
              </a-popconfirm>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ClockCircleOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import request from '@/utils/request'
import { checkLLMModule } from '@/composables/useLLMStatus'

const router = useRouter()
const loadingExams = ref(false)
const availableExams = ref<any[]>([])
const session = ref<any>(null)
const questions = ref<any[]>([])
const answers = reactive<Record<string, string>>({})
const markedSet = ref(new Set<string>())
const currentIndex = ref(0)
const remainingSeconds = ref<number | null>(null)
let timerInterval: any = null

// In-progress session recovery
const inProgressSession = ref<any>(null)
const resumingExam = ref(false)

// Random test state
const randomTestModalVisible = ref(false)
const randomTestLoading = ref(false)
const randomTestForm = reactive({ count: 10, difficulty_mode: 'real' })
const isRandomTest = ref(false)
const randomTestResult = ref<any>(null)
const cleanupLoading = ref(false)

const currentQuestion = computed(() => questions.value[currentIndex.value] || null)
const answeredCount = computed(() => questions.value.filter(q => answers[q.question_id]).length)

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
  return { single_choice: '单选题', multiple_choice: '多选题', true_false: '判断题', fill_blank: '填空题', short_answer: '简答题' }[t] || t
}

function formatTime(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

async function checkInProgressSession() {
  try {
    const sessions: any[] = await request.get('/sessions', { params: { skip: 0, limit: 10 } })
    const active = sessions.find((s: any) => s.status === 'in_progress')
    if (active) {
      inProgressSession.value = active
    }
  } catch { /* ignore */ }
}

async function resumeExam(activeSession: any) {
  resumingExam.value = true
  try {
    const sheetId = activeSession.id
    const sessionData: any = await request.get(`/sessions/${sheetId}`)

    session.value = {
      answer_sheet_id: sheetId,
      exam_id: activeSession.exam_id,
      exam_title: activeSession.exam_title || sessionData.exam_title,
      time_limit_minutes: sessionData.time_limit_minutes,
      start_time: activeSession.start_time || sessionData.start_time,
    }
    questions.value = sessionData.questions || []
    currentIndex.value = 0

    // Restore existing answers
    if (sessionData.answers) {
      for (const [qid, ans] of Object.entries(sessionData.answers)) {
        answers[qid] = ans as string
      }
      // Jump to first unanswered question
      const firstUnanswered = questions.value.findIndex(q => !answers[q.question_id])
      if (firstUnanswered >= 0) currentIndex.value = firstUnanswered
    }

    // Resume timer
    if (sessionData.time_limit_minutes) {
      const elapsed = Math.floor((Date.now() - new Date(session.value.start_time).getTime()) / 1000)
      remainingSeconds.value = Math.max(0, sessionData.time_limit_minutes * 60 - elapsed)
      startTimer()
    }

    // Save to sessionStorage for page navigation recovery
    sessionStorage.setItem('activeExamSession', JSON.stringify({ sheetId, examId: activeSession.exam_id }))
    inProgressSession.value = null
    message.success('已恢复考试，继续作答')
  } catch {
    message.error('恢复考试失败')
  } finally {
    resumingExam.value = false
  }
}

async function tryAutoRestore() {
  // Check sessionStorage for active session from page navigation
  const saved = sessionStorage.getItem('activeExamSession')
  if (saved) {
    try {
      const { sheetId } = JSON.parse(saved)
      const sessionData: any = await request.get(`/sessions/${sheetId}`)
      if (sessionData && sessionData.questions?.length > 0) {
        await resumeExam({ id: sheetId, exam_id: sessionData.exam_id, exam_title: sessionData.exam_title, start_time: sessionData.start_time })
        return true
      }
    } catch {
      // Session no longer valid, clean up
      sessionStorage.removeItem('activeExamSession')
    }
  }
  return false
}

async function fetchAvailableExams() {
  loadingExams.value = true
  try {
    const data: any = await request.get('/exams', { params: { status: 'published', skip: 0, limit: 50 } })
    availableExams.value = (data.items || []).filter((e: any) => !e.title.startsWith('随机测试'))
  } catch { /* handled */ } finally {
    loadingExams.value = false
  }
}

async function startExam(examId: string) {
  try {
    const data: any = await request.post(`/sessions/start/${examId}`)
    session.value = data

    // Load session data with questions
    const sessionData: any = await request.get(`/sessions/${data.answer_sheet_id}`)
    questions.value = sessionData.questions || []
    // Restore existing answers
    if (sessionData.answers) {
      for (const [qid, ans] of Object.entries(sessionData.answers)) {
        answers[qid] = ans as string
      }
    }

    // Start timer
    if (data.time_limit_minutes) {
      const elapsed = Math.floor((Date.now() - new Date(data.start_time).getTime()) / 1000)
      remainingSeconds.value = Math.max(0, data.time_limit_minutes * 60 - elapsed)
      startTimer()
    }
    // Persist to sessionStorage for navigation recovery
    sessionStorage.setItem('activeExamSession', JSON.stringify({ sheetId: data.answer_sheet_id, examId: examId }))
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
  // Warn if scoring LLM is not configured (subjective questions may score inaccurately)
  await checkLLMModule('scoring', '智能评分')
  try {
    const sheetId = session.value.answer_sheet_id
    const data: any = await request.post(`/sessions/${sheetId}/submit`)
    clearInterval(timerInterval)

    sessionStorage.removeItem('activeExamSession')

    if (isRandomTest.value) {
      // Fetch score and show inline — don't save to history
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
        // If score fetch fails, show basic result
        randomTestResult.value = {
          total_score: 0, max_score: 100, level: '—',
          ratio: 0, correct_count: 0,
          total_questions: data.total_questions,
          sheet_id: sheetId,
        }
      }
      session.value = null
      questions.value = []
      Object.keys(answers).forEach(k => delete answers[k])
    } else {
      message.success(`交卷成功！已答 ${data.total_answered}/${data.total_questions} 题`)
      session.value = null
      questions.value = []
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

    // Load session data with questions
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
  } catch { /* silent cleanup */ }
  cleanupLoading.value = false
  randomTestResult.value = null
  isRandomTest.value = false
  fetchAvailableExams()
}

onMounted(async () => {
  // Try to auto-restore an active exam session (from page navigation)
  const restored = await tryAutoRestore()
  if (!restored) {
    await fetchAvailableExams()
    await checkInProgressSession()
  }
})
onUnmounted(() => { if (timerInterval) clearInterval(timerInterval) })
</script>

<style scoped>
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
.question-header { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
.question-num { font-size: 16px; font-weight: 600; }
.question-stem { font-size: 15px; line-height: 1.8; margin-bottom: 20px; white-space: pre-wrap; }
.question-options { margin-bottom: 24px; }
.option-item { display: block; margin-bottom: 12px; font-size: 14px; line-height: 1.6; }
.question-actions { display: flex; gap: 12px; margin-top: 24px; }
</style>
