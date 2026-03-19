<template>
  <div class="page-container exam-compose-page">
    <div class="page-header">
      <div>
        <h2>{{ exam?.title || '试卷编排' }}</h2>
        <div class="page-subtitle">
          发布前可移除题目、补题、调整顺序和分值，保存后再发布
        </div>
      </div>
      <a-space>
        <a-tag :color="statusColor(exam?.status || 'draft')">{{ statusLabel(exam?.status || 'draft') }}</a-tag>
        <a-tag v-if="hasUnsavedChanges" color="warning">有未保存更改</a-tag>
        <a-button @click="discardChanges" :disabled="!hasUnsavedChanges">放弃更改</a-button>
        <a-button type="primary" @click="saveComposition" :loading="saving" :disabled="!hasUnsavedChanges">保存草稿</a-button>
        <a-button
          type="primary"
          style="background: #52c41a; border-color: #52c41a"
          @click="publishExam"
          :loading="publishing"
          :disabled="!canPublish"
        >
          发布考试
        </a-button>
      </a-space>
    </div>

    <a-card :bordered="false" class="summary-card" :loading="pageLoading">
      <a-row :gutter="16">
        <a-col :span="6">
          <a-statistic title="题目数量" :value="items.length" />
        </a-col>
        <a-col :span="6">
          <a-statistic title="总分" :value="totalScore" :precision="2" />
        </a-col>
        <a-col :span="6">
          <a-statistic title="考试时长" :value="exam?.time_limit_minutes || 0" suffix="分钟" />
        </a-col>
        <a-col :span="6">
          <a-statistic title="候选题数" :value="candidatePagination.total" />
        </a-col>
      </a-row>
      <a-alert
        v-if="!items.length"
        type="warning"
        show-icon
        message="当前试卷还没有题目，需先加入至少 1 道已审核通过题目后才能保存和发布"
        style="margin-top: 16px"
      />
    </a-card>

    <a-row :gutter="16" class="compose-layout">
      <a-col :xs="24" :xl="14">
        <a-card :bordered="false" title="当前试卷" class="compose-card" :loading="pageLoading">
          <template #extra>
            <span class="card-extra">共 {{ items.length }} 题 / {{ totalScore.toFixed(2) }} 分</span>
          </template>

          <a-empty v-if="!items.length" description="当前试卷暂无题目，请从右侧候选池补题" />

          <div v-else class="current-list">
            <div
              v-for="item in items"
              :key="item.local_key"
              class="current-item"
              :class="{ active: item.local_key === activeCurrentKey }"
              @click="selectCurrent(item.local_key)"
            >
              <div class="current-item-header">
                <div class="current-item-title">
                  <span class="order-badge">{{ item.order_num }}</span>
                  <span class="stem-text">{{ excerpt(item.question.stem) }}</span>
                </div>
                <a-space size="small">
                  <a-button size="small" @click.stop="moveItem(item.local_key, 'top')" :disabled="item.order_num === 1">置顶</a-button>
                  <a-button size="small" @click.stop="moveItem(item.local_key, 'up')" :disabled="item.order_num === 1">
                    <template #icon><ArrowUpOutlined /></template>
                  </a-button>
                  <a-button size="small" @click.stop="moveItem(item.local_key, 'down')" :disabled="item.order_num === items.length">
                    <template #icon><ArrowDownOutlined /></template>
                  </a-button>
                  <a-button size="small" @click.stop="moveItem(item.local_key, 'bottom')" :disabled="item.order_num === items.length">置底</a-button>
                  <a-popconfirm title="确认移除这道题？" @confirm="removeItem(item.local_key)">
                    <a-button size="small" danger @click.stop>移除</a-button>
                  </a-popconfirm>
                </a-space>
              </div>

              <div class="current-item-meta">
                <a-space wrap>
                  <a-tag :color="typeColor(item.question.question_type)">{{ typeLabel(item.question.question_type) }}</a-tag>
                  <a-tag v-if="item.question.dimension" color="blue">{{ item.question.dimension }}</a-tag>
                  <a-tag color="gold">难度 {{ item.question.difficulty }}</a-tag>
                </a-space>
                <div class="score-editor">
                  <span>分值</span>
                  <a-input-number
                    :value="item.score"
                    :min="0.5"
                    :step="0.5"
                    size="small"
                    @change="(value: string | number | null) => handleScoreChange(item.local_key, value)"
                  />
                </div>
              </div>
            </div>
          </div>

          <template v-if="activeCurrentItem">
            <a-divider />
            <div class="preview-section">
              <div class="preview-header">
                <span>当前选中题目预览</span>
                <span class="preview-subtitle">替换操作会保持当前题号与分值</span>
              </div>
              <div class="preview-body">
                <div class="preview-tags">
                  <a-tag :color="typeColor(activeCurrentItem.question.question_type)">{{ typeLabel(activeCurrentItem.question.question_type) }}</a-tag>
                  <a-tag v-if="activeCurrentItem.question.dimension" color="blue">{{ activeCurrentItem.question.dimension }}</a-tag>
                  <a-tag color="gold">难度 {{ activeCurrentItem.question.difficulty }}</a-tag>
                </div>
                <div class="preview-stem">{{ activeCurrentItem.question.stem }}</div>
                <div v-if="activeCurrentItem.question.options" class="option-list">
                  <div v-for="(value, key) in activeCurrentItem.question.options" :key="key" class="option-row">
                    <strong>{{ key }}.</strong> {{ value }}
                  </div>
                </div>
                <div v-if="activeCurrentItem.question.explanation" class="preview-explanation">
                  解析：{{ activeCurrentItem.question.explanation }}
                </div>
              </div>
            </div>
          </template>
        </a-card>
      </a-col>

      <a-col :xs="24" :xl="10">
        <a-card :bordered="false" title="候选题池" class="compose-card">
          <a-form layout="vertical">
            <a-row :gutter="12">
              <a-col :span="24">
                <a-form-item label="关键词">
                  <a-input
                    v-model:value="candidateFilters.keyword"
                    placeholder="搜索题干关键词"
                    allow-clear
                    @press-enter="refreshCandidates"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="题型">
                  <a-select v-model:value="candidateFilters.question_type" placeholder="不限题型" allow-clear>
                    <a-select-option value="single_choice">单选题</a-select-option>
                    <a-select-option value="multiple_choice">多选题</a-select-option>
                    <a-select-option value="true_false">判断题</a-select-option>
                    <a-select-option value="fill_blank">填空题</a-select-option>
                    <a-select-option value="short_answer">简答题</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="维度">
                  <a-select v-model:value="candidateFilters.dimension" placeholder="不限维度" allow-clear>
                    <a-select-option value="AI基础知识">AI基础知识</a-select-option>
                    <a-select-option value="AI技术应用">AI技术应用</a-select-option>
                    <a-select-option value="AI伦理安全">AI伦理安全</a-select-option>
                    <a-select-option value="AI批判思维">AI批判思维</a-select-option>
                    <a-select-option value="AI创新实践">AI创新实践</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="难度">
                  <a-select v-model:value="candidateFilters.difficulty" placeholder="不限难度" allow-clear>
                    <a-select-option :value="1">1</a-select-option>
                    <a-select-option :value="2">2</a-select-option>
                    <a-select-option :value="3">3</a-select-option>
                    <a-select-option :value="4">4</a-select-option>
                    <a-select-option :value="5">5</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="12" class="candidate-actions">
                <a-space>
                  <a-button type="primary" @click="refreshCandidates">筛选</a-button>
                  <a-button @click="resetCandidateFilters">重置</a-button>
                </a-space>
              </a-col>
            </a-row>
          </a-form>

          <a-list
            class="candidate-list"
            :loading="candidateLoading"
            :data-source="candidates"
            :locale="{ emptyText: '没有符合条件的候选题' }"
          >
            <template #renderItem="{ item }">
              <a-list-item class="candidate-item" :class="{ active: item.id === activeCandidateId }" @click="selectCandidate(item.id)">
                <template #actions>
                  <a-button type="link" size="small" @click.stop="addCandidate(item)">加入试卷</a-button>
                  <a-button type="link" size="small" @click.stop="replaceSelected(item)" :disabled="!activeCurrentItem">
                    替换当前题
                  </a-button>
                </template>
                <a-list-item-meta :description="item.dimension || '未分类'">
                  <template #title>
                    <div class="candidate-title">
                      <span>{{ excerpt(item.stem, 30) }}</span>
                      <a-space size="small">
                        <a-tag :color="typeColor(item.question_type)">{{ typeLabel(item.question_type) }}</a-tag>
                        <a-tag color="gold">难度 {{ item.difficulty }}</a-tag>
                      </a-space>
                    </div>
                  </template>
                </a-list-item-meta>
              </a-list-item>
            </template>
          </a-list>

          <a-pagination
            v-model:current="candidatePagination.current"
            :page-size="candidatePagination.pageSize"
            :total="candidatePagination.total"
            size="small"
            style="margin-top: 12px; text-align: right"
            @change="fetchCandidates"
          />

          <a-divider />

          <div class="preview-section">
            <div class="preview-header">
              <span>候选题预览</span>
              <span class="preview-subtitle">候选题池默认排除了当前已入卷题目</span>
            </div>
            <a-empty v-if="!activeCandidate" description="选择候选题后显示完整预览" />
            <template v-else>
              <div class="preview-body">
                <div class="preview-tags">
                  <a-tag :color="typeColor(activeCandidate.question_type)">{{ typeLabel(activeCandidate.question_type) }}</a-tag>
                  <a-tag v-if="activeCandidate.dimension" color="blue">{{ activeCandidate.dimension }}</a-tag>
                  <a-tag color="gold">难度 {{ activeCandidate.difficulty }}</a-tag>
                </div>
                <div class="preview-stem">{{ activeCandidate.stem }}</div>
                <div v-if="activeCandidate.options" class="option-list">
                  <div v-for="(value, key) in activeCandidate.options" :key="key" class="option-row">
                    <strong>{{ key }}.</strong> {{ value }}
                  </div>
                </div>
                <div v-if="activeCandidate.explanation" class="preview-explanation">
                  解析：{{ activeCandidate.explanation }}
                </div>
              </div>
            </template>
          </div>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons-vue'
import request from '@/utils/request'

interface CandidateQuestion {
  id: string
  question_type: string
  stem: string
  options?: Record<string, string> | null
  correct_answer: string
  explanation?: string | null
  difficulty: number
  dimension?: string | null
  status: string
}

interface CompositionItem {
  local_key: string
  question_id: string
  order_num: number
  score: number
  question: CandidateQuestion
}

const route = useRoute()
const router = useRouter()
const examId = computed(() => String(route.params.examId || ''))

const pageLoading = ref(false)
const candidateLoading = ref(false)
const saving = ref(false)
const publishing = ref(false)

const exam = ref<any>(null)
const items = ref<CompositionItem[]>([])
const candidates = ref<CandidateQuestion[]>([])

const activeCurrentKey = ref<string | null>(null)
const activeCandidateId = ref<string | null>(null)
const savedSignature = ref('[]')
const lastEditedScore = ref<number | null>(null)
const candidatePagination = reactive({ current: 1, pageSize: 10, total: 0 })
const candidateFilters = reactive({
  keyword: '',
  question_type: undefined as string | undefined,
  dimension: undefined as string | undefined,
  difficulty: undefined as number | undefined,
})

let keySeed = 0

function nextLocalKey() {
  keySeed += 1
  return `composer-${keySeed}`
}

function statusColor(status: string) {
  return { draft: 'default', published: 'green', closed: 'orange' }[status] || 'default'
}

function statusLabel(status: string) {
  return { draft: '草稿', published: '已发布', closed: '已关闭' }[status] || status
}

function typeLabel(type: string) {
  return {
    single_choice: '单选题',
    multiple_choice: '多选题',
    true_false: '判断题',
    fill_blank: '填空题',
    short_answer: '简答题',
  }[type] || type
}

function typeColor(type: string) {
  return {
    single_choice: 'blue',
    multiple_choice: 'purple',
    true_false: 'green',
    fill_blank: 'orange',
    short_answer: 'cyan',
  }[type] || 'default'
}

function excerpt(text: string, max = 42) {
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max)}...` : text
}

function compositionPayload() {
  return items.value.map((item, index) => ({
    question_id: item.question_id,
    order_num: index + 1,
    score: Number(item.score),
  }))
}

function compositionSignature() {
  return JSON.stringify(compositionPayload())
}

function applyItems(nextItems: CompositionItem[]) {
  items.value = nextItems.map((item, index) => ({
    ...item,
    order_num: index + 1,
  }))

  if (!items.value.find(item => item.local_key === activeCurrentKey.value)) {
    activeCurrentKey.value = items.value[0]?.local_key || null
  }
}

function applyCompositionResponse(data: any) {
  exam.value = data.exam
  applyItems(
    (data.items || []).map((item: any) => ({
      local_key: item.id || nextLocalKey(),
      question_id: item.question_id,
      order_num: item.order_num,
      score: item.score,
      question: item.question,
    }))
  )
  savedSignature.value = compositionSignature()
}

const totalScore = computed(() => items.value.reduce((sum, item) => sum + Number(item.score || 0), 0))
const hasUnsavedChanges = computed(() => compositionSignature() !== savedSignature.value)
const activeCurrentItem = computed(() => items.value.find(item => item.local_key === activeCurrentKey.value) || null)
const activeCandidate = computed(() => candidates.value.find(item => item.id === activeCandidateId.value) || null)
const canPublish = computed(() => {
  return exam.value?.status === 'draft'
    && !hasUnsavedChanges.value
    && items.value.length > 0
    && items.value.every(item => Number(item.score) > 0)
})

async function loadComposition() {
  pageLoading.value = true
  try {
    const data: any = await request.get(`/exams/${examId.value}/composition`)
    applyCompositionResponse(data)
  } catch {
    router.push({ name: 'Exams' })
  } finally {
    pageLoading.value = false
  }
}

function buildCandidateParams() {
  const params = new URLSearchParams()
  params.set('status', 'approved')
  params.set('skip', String((candidatePagination.current - 1) * candidatePagination.pageSize))
  params.set('limit', String(candidatePagination.pageSize))
  if (candidateFilters.keyword) params.set('keyword', candidateFilters.keyword)
  if (candidateFilters.question_type) params.set('question_type', candidateFilters.question_type)
  if (candidateFilters.dimension) params.set('dimension', candidateFilters.dimension)
  if (candidateFilters.difficulty) params.set('difficulty', String(candidateFilters.difficulty))
  items.value.forEach(item => params.append('exclude_ids', item.question_id))
  return params
}

async function fetchCandidates() {
  candidateLoading.value = true
  try {
    const data: any = await request.get('/questions', { params: buildCandidateParams() })
    candidates.value = data.items || []
    candidatePagination.total = data.total || 0
    if (!candidates.value.find(item => item.id === activeCandidateId.value)) {
      activeCandidateId.value = candidates.value[0]?.id || null
    }
  } finally {
    candidateLoading.value = false
  }
}

function refreshCandidates() {
  candidatePagination.current = 1
  fetchCandidates()
}

function resetCandidateFilters() {
  candidateFilters.keyword = ''
  candidateFilters.question_type = undefined
  candidateFilters.dimension = undefined
  candidateFilters.difficulty = undefined
  refreshCandidates()
}

function selectCurrent(localKey: string) {
  activeCurrentKey.value = localKey
}

function selectCandidate(candidateId: string) {
  activeCandidateId.value = candidateId
}

function removeItem(localKey: string) {
  applyItems(items.value.filter(item => item.local_key !== localKey))
  refreshCandidates()
}

function moveItem(localKey: string, direction: 'up' | 'down' | 'top' | 'bottom') {
  const nextItems = [...items.value]
  const index = nextItems.findIndex(item => item.local_key === localKey)
  if (index < 0) return

  const [target] = nextItems.splice(index, 1)
  if (!target) return
  if (direction === 'up') nextItems.splice(Math.max(index - 1, 0), 0, target)
  if (direction === 'down') nextItems.splice(Math.min(index + 1, nextItems.length), 0, target)
  if (direction === 'top') nextItems.unshift(target)
  if (direction === 'bottom') nextItems.push(target)
  applyItems(nextItems)
}

function handleScoreChange(localKey: string, value: string | number | null) {
  if (typeof value !== 'number' || value <= 0) return
  const item = items.value.find(entry => entry.local_key === localKey)
  if (!item) return
  item.score = value
  lastEditedScore.value = value
}

function addCandidate(candidate: CandidateQuestion) {
  if (items.value.some(item => item.question_id === candidate.id)) {
    message.warning('这道题已经在当前试卷中')
    return
  }
  applyItems([
    ...items.value,
    {
      local_key: nextLocalKey(),
      question_id: candidate.id,
      order_num: items.value.length + 1,
      score: lastEditedScore.value ?? 5,
      question: candidate,
    },
  ])
  activeCurrentKey.value = items.value[items.value.length - 1]?.local_key || null
  refreshCandidates()
}

function replaceSelected(candidate: CandidateQuestion) {
  if (!activeCurrentItem.value) {
    message.warning('请先在左侧选择要替换的题目')
    return
  }
  if (items.value.some(item => item.question_id === candidate.id)) {
    message.warning('这道题已经在当前试卷中')
    return
  }

  applyItems(items.value.map(item => {
    if (item.local_key !== activeCurrentKey.value) return item
    return {
      ...item,
      question_id: candidate.id,
      question: candidate,
    }
  }))
  refreshCandidates()
}

async function saveComposition() {
  saving.value = true
  try {
    const data: any = await request.put(`/exams/${examId.value}/composition`, {
      items: compositionPayload(),
    })
    applyCompositionResponse(data)
    message.success('试卷编排已保存')
    await fetchCandidates()
  } catch {
    // handled by interceptor
  } finally {
    saving.value = false
  }
}

async function publishExam() {
  if (hasUnsavedChanges.value) {
    message.warning('请先保存编排结果，再发布考试')
    return
  }
  publishing.value = true
  try {
    await request.post(`/exams/${examId.value}/publish`)
    message.success('试卷已发布')
    router.push({ name: 'Exams' })
  } catch {
    // handled by interceptor
  } finally {
    publishing.value = false
  }
}

async function discardChanges() {
  if (!hasUnsavedChanges.value) return
  if (!window.confirm('确认放弃当前未保存的编排更改？')) return
  await loadComposition()
  await fetchCandidates()
}

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!hasUnsavedChanges.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave((_to, _from, next) => {
  if (!hasUnsavedChanges.value || window.confirm('当前有未保存更改，确认离开？')) {
    next()
    return
  }
  next(false)
})

onMounted(async () => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  await loadComposition()
  await fetchCandidates()
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
})
</script>

<style scoped>
.exam-compose-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-subtitle {
  color: #666;
  margin-top: 4px;
}

.summary-card {
  margin-bottom: 0;
}

.compose-layout {
  margin-bottom: 8px;
}

.compose-card {
  height: 100%;
}

.card-extra {
  color: #666;
  font-size: 12px;
}

.current-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.current-item,
.candidate-item {
  border: 1px solid #eef2f6;
  border-radius: 10px;
  padding: 12px;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  cursor: pointer;
}

.current-item.active,
.candidate-item.active {
  border-color: #1f4e79;
  box-shadow: 0 0 0 2px rgba(31, 78, 121, 0.12);
}

.current-item-header,
.current-item-meta,
.candidate-title,
.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.current-item-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.order-badge {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: #1f4e79;
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  flex: 0 0 auto;
}

.stem-text {
  font-weight: 500;
}

.score-editor {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #666;
}

.candidate-actions {
  display: flex;
  align-items: end;
  justify-content: flex-end;
}

.candidate-list {
  margin-top: 4px;
}

.preview-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.preview-subtitle {
  color: #888;
  font-size: 12px;
}

.preview-body {
  background: #fafbfc;
  border-radius: 10px;
  padding: 16px;
}

.preview-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.preview-stem {
  font-size: 15px;
  line-height: 1.7;
  color: #1f1f1f;
  margin-bottom: 12px;
}

.option-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.option-row {
  padding: 8px 10px;
  background: #fff;
  border: 1px solid #edf0f3;
  border-radius: 8px;
}

.preview-explanation {
  margin-top: 12px;
  color: #666;
  line-height: 1.6;
}

@media (max-width: 1200px) {
  .current-item-header,
  .current-item-meta,
  .candidate-title,
  .preview-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .candidate-actions {
    justify-content: flex-start;
  }
}
</style>
