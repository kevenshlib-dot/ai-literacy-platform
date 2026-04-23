<template>
  <div class="page-container exam-compose-page">
    <div class="workspace-toolbar">
      <div class="toolbar-nav">
        <a-button class="back-button" @click="goBackToExams">
          <template #icon><ArrowLeftOutlined /></template>
          返回考试管理
        </a-button>
        <a-breadcrumb>
          <a-breadcrumb-item>考试管理</a-breadcrumb-item>
          <a-breadcrumb-item>试卷编排</a-breadcrumb-item>
        </a-breadcrumb>
      </div>

      <div class="toolbar-main">
        <div class="toolbar-summary">
          <div class="toolbar-title">
            <h2>{{ exam?.title || '试卷编排' }}</h2>
            <a-space wrap>
              <a-tag :color="statusColor(exam?.status || 'draft')">{{ statusLabel(exam?.status || 'draft') }}</a-tag>
              <a-tag v-if="hasUnsavedChanges" color="warning">有未保存更改</a-tag>
            </a-space>
          </div>
          <div class="toolbar-stats">
            <div class="stat-chip">
              <span class="stat-label">题目数</span>
              <strong>{{ items.length }}</strong>
            </div>
            <div class="stat-chip">
              <span class="stat-label">总分</span>
              <strong>{{ totalScore }}</strong>
            </div>
            <div class="stat-chip">
              <span class="stat-label">考试时长</span>
              <strong>{{ exam?.time_limit_minutes || 0 }} 分钟</strong>
            </div>
            <div class="stat-chip">
              <span class="stat-label">候选题</span>
              <strong>{{ candidatePagination.total }}</strong>
            </div>
          </div>
        </div>

        <a-space class="toolbar-actions" wrap>
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
    </div>

    <a-alert
      v-if="!items.length"
      type="warning"
      show-icon
      message="当前试卷还没有题目，需先加入至少 1 道已审核通过题目后才能保存和发布"
    />

    <a-row :gutter="20" class="workspace-layout">
      <a-col :xs="24" :xl="14">
        <a-card :bordered="false" class="workspace-panel" :loading="pageLoading">
          <template #title>
            <div class="panel-title">
              <span>当前试卷</span>
              <span class="panel-subtitle">按题型分组编排，组内支持拖拽排序</span>
            </div>
          </template>

          <a-empty v-if="!groupedItems.length" description="当前试卷暂无题目，请从右侧候选题池加入题目" />

          <div v-else class="group-list">
            <section v-for="group in groupedItems" :key="group.questionType" class="group-section">
              <div class="group-header">
                <div class="group-title">
                  <span>{{ group.title }}</span>
                  <a-tag>{{ group.count }} 题</a-tag>
                </div>
                <div class="group-header-actions">
                  <a-space size="small">
                    <a-button
                      size="small"
                      @click="moveGroupUp(group.questionType)"
                      :disabled="!canMoveGroupUp(group.questionType)"
                    >
                      <template #icon><ArrowUpOutlined /></template>
                      上移
                    </a-button>
                    <a-button
                      size="small"
                      @click="moveGroupDown(group.questionType)"
                      :disabled="!canMoveGroupDown(group.questionType)"
                    >
                      <template #icon><ArrowDownOutlined /></template>
                      下移
                    </a-button>
                  </a-space>
                  <div class="group-score">{{ group.subtotalScore }} 分</div>
                </div>
              </div>

              <div class="group-items">
                <article
                  v-for="item in group.items"
                  :key="item.local_key"
                  class="question-card current-card"
                  :class="{
                    active: item.local_key === activeCurrentKey,
                    dragging: item.local_key === draggingKey,
                    over: item.local_key === dragOverKey,
                  }"
                  draggable="true"
                  @click="selectCurrent(item.local_key)"
                  @dragstart="handleDragStart($event, item.local_key, group.questionType)"
                  @dragend="handleDragEnd"
                  @dragover="handleDragOver($event, item.local_key, group.questionType)"
                  @drop="handleDrop($event, item.local_key, group.questionType)"
                >
                  <div class="card-topline">
                    <div class="card-order">
                      <span class="order-badge">{{ orderMap.get(item.local_key) }}</span>
                      <HolderOutlined class="drag-icon" />
                      <span class="drag-text">拖拽排序</span>
                    </div>
                    <div class="card-controls">
                      <div class="score-editor">
                        <span>分值</span>
                        <a-input-number
                          :value="item.score"
                          :min="1"
                          :step="1"
                          :precision="0"
                          size="small"
                          @click.stop
                          @change="(value: string | number | null) => handleScoreChange(item.local_key, value)"
                        />
                      </div>
                      <a-popconfirm title="确认移除这道题？" @confirm="removeItem(item.local_key)">
                        <a-button size="small" danger class="card-button" @click.stop>移除</a-button>
                      </a-popconfirm>
                    </div>
                  </div>

                  <div class="card-stem">{{ item.question.stem }}</div>

                  <div class="card-meta-row">
                    <div class="meta-tags">
                      <a-tag :color="typeColor(item.question.question_type)">{{ typeLabel(item.question.question_type) }}</a-tag>
                      <a-tag color="gold">难度 {{ item.question.difficulty }}</a-tag>
                      <a-tag v-if="item.question.dimension" color="blue">{{ item.question.dimension }}</a-tag>
                    </div>
                  </div>
                </article>

                <div
                  class="group-dropzone"
                  :class="{ active: dragOverGroupType === group.questionType && dragOverKey === null }"
                  @dragover="handleGroupDragOver($event, group.questionType)"
                  @drop="handleGroupDropToEnd($event, group.questionType)"
                >
                  拖到此处可移动到本组末尾
                </div>
              </div>
            </section>
          </div>
        </a-card>
      </a-col>

      <a-col :xs="24" :xl="10">
        <a-card :bordered="false" class="workspace-panel">
          <template #title>
            <div class="panel-title">
              <span>候选题池</span>
              <span class="panel-subtitle">题干完整展示，右侧直接加入或替换</span>
            </div>
          </template>

          <a-alert
            v-if="activeCurrentItem"
            type="info"
            show-icon
            class="selection-alert"
            :message="`当前已选中 ${typeLabel(activeCurrentItem.question.question_type)}，可替换同题型候选题`"
          />

          <a-form layout="vertical" class="candidate-filter">
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
              <a-col :span="24">
                <a-form-item label="知识维度">
                  <a-select v-model:value="candidateFilters.dimension" placeholder="不限知识维度" allow-clear>
                    <a-select-option value="AI基础知识">AI基础知识</a-select-option>
                    <a-select-option value="AI技术应用">AI技术应用</a-select-option>
                    <a-select-option value="AI伦理安全">AI伦理安全</a-select-option>
                    <a-select-option value="AI批判思维">AI批判思维</a-select-option>
                    <a-select-option value="AI创新实践">AI创新实践</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="24">
                <a-space>
                  <a-button type="primary" @click="refreshCandidates">筛选</a-button>
                  <a-button @click="resetCandidateFilters">重置</a-button>
                </a-space>
              </a-col>
            </a-row>
          </a-form>

          <div class="candidate-cards">
            <a-spin :spinning="candidateLoading">
              <div v-if="candidates.length" class="candidate-batch-bar">
                <div class="candidate-batch-info">
                  已选 {{ selectedCandidateIds.length }} 题
                </div>
                <a-space>
                  <a-button
                    type="primary"
                    size="small"
                    :disabled="!selectedCandidateIds.length"
                    @click="addSelectedCandidates"
                  >
                    批量加入试卷
                  </a-button>
                  <a-button
                    size="small"
                    :disabled="!selectedCandidateIds.length"
                    @click="clearSelectedCandidates"
                  >
                    清空选择
                  </a-button>
                </a-space>
              </div>
              <a-empty v-if="!candidates.length" description="没有符合条件的候选题" />

              <div v-else class="candidate-list">
                <article
                  v-for="candidate in candidates"
                  :key="candidate.id"
                  class="question-card candidate-card"
                  :class="{ active: candidate.id === activeCandidateId }"
                  @click="selectCandidate(candidate.id)"
                >
                  <div class="card-topline">
                    <div class="candidate-title-row">
                      <a-checkbox
                        :checked="isCandidateSelected(candidate.id)"
                        @click.stop
                        @change="() => toggleCandidateSelection(candidate)"
                      />
                      <div class="candidate-title-text">候选题</div>
                    </div>
                    <div class="card-controls">
                      <a-button
                        size="small"
                        type="primary"
                        class="card-button"
                        @click.stop="handlePrimaryCandidateAction(candidate)"
                      >
                        {{ activeCurrentItem ? '替换当前题' : '加入试卷' }}
                      </a-button>
                      <a-button
                        v-if="activeCurrentItem"
                        size="small"
                        class="card-button"
                        @click.stop="addCandidate(candidate)"
                      >
                        加入试卷
                      </a-button>
                    </div>
                  </div>

                  <div class="card-stem">{{ candidate.stem }}</div>

                  <div class="card-meta-row">
                    <div class="meta-tags">
                      <a-tag :color="typeColor(candidate.question_type)">{{ typeLabel(candidate.question_type) }}</a-tag>
                      <a-tag color="gold">难度 {{ candidate.difficulty }}</a-tag>
                      <a-tag v-if="candidate.dimension" color="blue">{{ candidate.dimension }}</a-tag>
                    </div>
                  </div>
                </article>
              </div>
            </a-spin>
          </div>

          <a-pagination
            v-model:current="candidatePagination.current"
            :page-size="candidatePagination.pageSize"
            :total="candidatePagination.total"
            size="small"
            style="margin-top: 16px; text-align: right"
            @change="fetchCandidates"
          />
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowDownOutlined, ArrowLeftOutlined, ArrowUpOutlined, HolderOutlined } from '@ant-design/icons-vue'
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

interface CompositionGroup {
  questionType: string
  title: string
  items: CompositionItem[]
  count: number
  subtotalScore: number
}

const DEFAULT_QUESTION_TYPE_ORDER = [
  'single_choice',
  'multiple_choice',
  'true_false',
  'fill_blank',
  'short_answer',
]

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
const selectedCandidateIds = ref<string[]>([])
const groupOrder = ref<string[]>([])
const savedSignature = ref('[]')
const candidatePagination = reactive({ current: 1, pageSize: 10, total: 0 })
const candidateFilters = reactive({
  keyword: '',
  question_type: undefined as string | undefined,
  dimension: undefined as string | undefined,
  difficulty: undefined as number | undefined,
})

const draggingKey = ref<string | null>(null)
const draggingGroupType = ref<string | null>(null)
const dragOverKey = ref<string | null>(null)
const dragOverGroupType = ref<string | null>(null)

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

function returnToPath() {
  return typeof route.query.returnTo === 'string' ? route.query.returnTo : '/exams'
}

function createBuckets(source: CompositionItem[]) {
  const buckets: Record<string, CompositionItem[]> = Object.fromEntries(
    DEFAULT_QUESTION_TYPE_ORDER.map(type => [type, [] as CompositionItem[]])
  )

  source.forEach(item => {
    const type = item.question.question_type
    if (!buckets[type]) {
      buckets[type] = []
    }
    buckets[type].push(item)
  })

  return buckets
}

function inferGroupOrder(source: CompositionItem[]) {
  return Array.from(new Set(source.map(item => item.question.question_type)))
}

function normalizeGroupOrder(source: CompositionItem[], preferredOrder: string[]) {
  const presentTypes = inferGroupOrder(source)
  const ordered = preferredOrder.filter(type => presentTypes.includes(type))
  const extras = presentTypes.filter(type => !ordered.includes(type))
  return [...ordered, ...extras]
}

function flattenBuckets(buckets: Record<string, CompositionItem[]>, order: string[]) {
  return order
    .flatMap(type => buckets[type] || [])
    .map((item, index) => ({
      ...item,
      order_num: index + 1,
      score: Math.max(1, Math.round(Number(item.score) || 1)),
    }))
}

function applyItems(nextItems: CompositionItem[], preferredOrder: string[] = groupOrder.value) {
  const nextGroupOrder = normalizeGroupOrder(nextItems, preferredOrder)
  groupOrder.value = nextGroupOrder
  items.value = flattenBuckets(createBuckets(nextItems), nextGroupOrder)
  if (!items.value.find(item => item.local_key === activeCurrentKey.value)) {
    activeCurrentKey.value = items.value[0]?.local_key || null
  }
}

function applyCompositionResponse(data: any) {
  exam.value = data.exam
  const nextItems = (data.items || []).map((item: any) => ({
      local_key: item.id || nextLocalKey(),
      question_id: item.question_id,
      order_num: item.order_num,
      score: Math.round(Number(item.score) || 1),
      question: item.question,
    }))
  applyItems(nextItems, inferGroupOrder(nextItems))
  savedSignature.value = compositionSignature()
}

const groupedItems = computed<CompositionGroup[]>(() => {
  const buckets = createBuckets(items.value)
  return groupOrder.value
    .map(questionType => {
      const groupItems = buckets[questionType] || []
      if (!groupItems.length) return null
      return {
        questionType,
        title: typeLabel(questionType),
        items: groupItems,
        count: groupItems.length,
        subtotalScore: groupItems.reduce((sum, item) => sum + item.score, 0),
      }
    })
    .filter((group): group is CompositionGroup => Boolean(group))
})

const orderMap = computed(() => {
  const map = new Map<string, number>()
  items.value.forEach((item, index) => map.set(item.local_key, index + 1))
  return map
})

function compositionPayload() {
  return items.value.map((item, index) => ({
    question_id: item.question_id,
    order_num: index + 1,
    score: Math.round(Number(item.score) || 1),
  }))
}

function compositionSignature() {
  return JSON.stringify(compositionPayload())
}

const totalScore = computed(() => items.value.reduce((sum, item) => sum + item.score, 0))
const hasUnsavedChanges = computed(() => compositionSignature() !== savedSignature.value)
const activeCurrentItem = computed(() => items.value.find(item => item.local_key === activeCurrentKey.value) || null)
const canPublish = computed(() => {
  return exam.value?.status === 'draft'
    && !hasUnsavedChanges.value
    && items.value.length > 0
    && items.value.every(item => Number.isInteger(item.score) && item.score > 0)
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
    selectedCandidateIds.value = selectedCandidateIds.value.filter(id => candidates.value.some(item => item.id === id))
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

async function refetchCandidatesKeepingPage() {
  await fetchCandidates()
  if (!candidates.value.length && candidatePagination.total > 0 && candidatePagination.current > 1) {
    candidatePagination.current -= 1
    await fetchCandidates()
  }
}

function resetCandidateFilters() {
  candidateFilters.keyword = ''
  candidateFilters.question_type = undefined
  candidateFilters.dimension = undefined
  candidateFilters.difficulty = undefined
  refreshCandidates()
}

function goBackToExams() {
  router.push(returnToPath())
}

function selectCurrent(localKey: string) {
  activeCurrentKey.value = localKey
}

function selectCandidate(candidateId: string) {
  activeCandidateId.value = candidateId
}

function clearSelectedCandidates() {
  selectedCandidateIds.value = []
}

function isCandidateSelected(candidateId: string) {
  return selectedCandidateIds.value.includes(candidateId)
}

function toggleCandidateSelection(candidate: CandidateQuestion) {
  if (isCandidateSelected(candidate.id)) {
    selectedCandidateIds.value = selectedCandidateIds.value.filter(id => id !== candidate.id)
    return
  }
  selectedCandidateIds.value = [...selectedCandidateIds.value, candidate.id]
}

async function removeItem(localKey: string) {
  applyItems(items.value.filter(item => item.local_key !== localKey))
  await refetchCandidatesKeepingPage()
}

function handleScoreChange(localKey: string, value: string | number | null) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return
  const item = items.value.find(entry => entry.local_key === localKey)
  if (!item) return
  item.score = Math.max(1, Math.round(value))
}

function defaultScoreForType(questionType: string) {
  const lastItem = [...items.value].reverse().find(item => item.question.question_type === questionType)
  return lastItem ? lastItem.score : 5
}

function appendGroupOrder(order: string[], questionType: string) {
  if (order.includes(questionType)) return [...order]
  return [...order, questionType]
}

function addCandidatesToComposition(candidateList: CandidateQuestion[]) {
  const existingIds = new Set(items.value.map(item => item.question_id))
  const freshCandidates = candidateList.filter(candidate => !existingIds.has(candidate.id))
  const skippedCount = candidateList.length - freshCandidates.length

  if (!freshCandidates.length) {
    message.warning('所选题目都已在当前试卷中')
    return []
  }

  const buckets = createBuckets(items.value)
  let nextGroupOrder = [...groupOrder.value]
  const insertedKeys: string[] = []

  freshCandidates.forEach(candidate => {
    nextGroupOrder = appendGroupOrder(nextGroupOrder, candidate.question_type)
    const targetBucket = buckets[candidate.question_type] ?? []
    const defaultScore = targetBucket[targetBucket.length - 1]?.score ?? defaultScoreForType(candidate.question_type)
    const newItem: CompositionItem = {
      local_key: nextLocalKey(),
      question_id: candidate.id,
      order_num: items.value.length + insertedKeys.length + 1,
      score: defaultScore,
      question: candidate,
    }
    targetBucket.push(newItem)
    buckets[candidate.question_type] = targetBucket
    insertedKeys.push(newItem.local_key)
  })

  applyItems(flattenBuckets(buckets, nextGroupOrder), nextGroupOrder)
  if (insertedKeys.length) {
    activeCurrentKey.value = insertedKeys[insertedKeys.length - 1] ?? null
  }
  if (skippedCount > 0) {
    message.info(`已加入 ${freshCandidates.length} 题，跳过 ${skippedCount} 题重复题目`)
  }
  return freshCandidates.map(candidate => candidate.id)
}

async function addCandidate(candidate: CandidateQuestion) {
  const addedIds = addCandidatesToComposition([candidate])
  if (!addedIds.length) return
  selectedCandidateIds.value = selectedCandidateIds.value.filter(id => !addedIds.includes(id))
  await refetchCandidatesKeepingPage()
}

function canReplaceSelected(candidate: CandidateQuestion) {
  return Boolean(
    activeCurrentItem.value
    && candidate.question_type === activeCurrentItem.value.question.question_type
  )
}

async function replaceSelected(candidate: CandidateQuestion) {
  if (!activeCurrentItem.value) {
    message.warning('请先在左侧选择要替换的题目')
    return
  }
  if (!canReplaceSelected(candidate)) {
    message.warning('替换当前题仅支持同题型候选题')
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
  selectedCandidateIds.value = selectedCandidateIds.value.filter(id => id !== candidate.id)
  await refetchCandidatesKeepingPage()
}

async function handlePrimaryCandidateAction(candidate: CandidateQuestion) {
  if (activeCurrentItem.value) {
    await replaceSelected(candidate)
    return
  }
  await addCandidate(candidate)
}

async function addSelectedCandidates() {
  const selectedCandidates = candidates.value.filter(candidate => selectedCandidateIds.value.includes(candidate.id))
  if (!selectedCandidates.length) {
    message.warning('请先选择要加入试卷的候选题')
    return
  }
  const addedIds = addCandidatesToComposition(selectedCandidates)
  if (!addedIds.length) return
  selectedCandidateIds.value = selectedCandidateIds.value.filter(id => !addedIds.includes(id))
  await refetchCandidatesKeepingPage()
}

function handleDragStart(event: DragEvent, localKey: string, groupType: string) {
  draggingKey.value = localKey
  draggingGroupType.value = groupType
  event.dataTransfer?.setData('text/plain', localKey)
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
  }
}

function handleDragOver(event: DragEvent, localKey: string, groupType: string) {
  if (!draggingKey.value || draggingGroupType.value !== groupType) return
  event.preventDefault()
  dragOverKey.value = localKey
  dragOverGroupType.value = groupType
}

function handleDrop(event: DragEvent, targetKey: string, groupType: string) {
  event.preventDefault()
  if (!draggingKey.value || draggingGroupType.value !== groupType || draggingKey.value === targetKey) {
    handleDragEnd()
    return
  }

  const buckets = createBuckets(items.value)
  const groupItems = [...(buckets[groupType] || [])]
  const fromIndex = groupItems.findIndex(item => item.local_key === draggingKey.value)
  const targetIndex = groupItems.findIndex(item => item.local_key === targetKey)
  if (fromIndex < 0 || targetIndex < 0) {
    handleDragEnd()
    return
  }

  const [movedItem] = groupItems.splice(fromIndex, 1)
  if (!movedItem) {
    handleDragEnd()
    return
  }
  groupItems.splice(targetIndex, 0, movedItem)
  buckets[groupType] = groupItems
  applyItems(flattenBuckets(buckets, groupOrder.value), groupOrder.value)
  activeCurrentKey.value = movedItem.local_key
  handleDragEnd()
}

function handleGroupDragOver(event: DragEvent, groupType: string) {
  if (!draggingKey.value || draggingGroupType.value !== groupType) return
  event.preventDefault()
  dragOverKey.value = null
  dragOverGroupType.value = groupType
}

function handleGroupDropToEnd(event: DragEvent, groupType: string) {
  event.preventDefault()
  if (!draggingKey.value || draggingGroupType.value !== groupType) {
    handleDragEnd()
    return
  }

  const buckets = createBuckets(items.value)
  const groupItems = [...(buckets[groupType] || [])]
  const fromIndex = groupItems.findIndex(item => item.local_key === draggingKey.value)
  if (fromIndex < 0) {
    handleDragEnd()
    return
  }

  const [movedItem] = groupItems.splice(fromIndex, 1)
  if (!movedItem) {
    handleDragEnd()
    return
  }
  groupItems.push(movedItem)
  buckets[groupType] = groupItems
  applyItems(flattenBuckets(buckets, groupOrder.value), groupOrder.value)
  activeCurrentKey.value = movedItem.local_key
  handleDragEnd()
}

function handleDragEnd() {
  draggingKey.value = null
  draggingGroupType.value = null
  dragOverKey.value = null
  dragOverGroupType.value = null
}

function canMoveGroupUp(questionType: string) {
  return groupOrder.value.indexOf(questionType) > 0
}

function canMoveGroupDown(questionType: string) {
  const index = groupOrder.value.indexOf(questionType)
  return index > -1 && index < groupOrder.value.length - 1
}

function moveGroupUp(questionType: string) {
  const index = groupOrder.value.indexOf(questionType)
  if (index <= 0) return
  const nextOrder = [...groupOrder.value]
  const currentType = nextOrder[index]
  const previousType = nextOrder[index - 1]
  if (!currentType || !previousType) return
  nextOrder[index - 1] = currentType
  nextOrder[index] = previousType
  applyItems(items.value, nextOrder)
}

function moveGroupDown(questionType: string) {
  const index = groupOrder.value.indexOf(questionType)
  if (index < 0 || index >= groupOrder.value.length - 1) return
  const nextOrder = [...groupOrder.value]
  const currentType = nextOrder[index]
  const nextType = nextOrder[index + 1]
  if (!currentType || !nextType) return
  nextOrder[index] = nextType
  nextOrder[index + 1] = currentType
  applyItems(items.value, nextOrder)
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
    router.push(returnToPath())
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

.workspace-toolbar {
  position: sticky;
  top: 0;
  z-index: 10;
  background: #f5f7fa;
  padding-bottom: 8px;
}

.toolbar-nav {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.back-button {
  border-radius: 999px;
}

.toolbar-main {
  background: linear-gradient(135deg, #f8fbff 0%, #eef4fb 100%);
  border: 1px solid #dbe6f2;
  border-radius: 18px;
  padding: 18px 20px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.toolbar-summary {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.toolbar-title {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.toolbar-title h2 {
  margin: 0;
}

.toolbar-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.stat-chip {
  min-width: 116px;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid #e6edf5;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-label {
  color: #6b7280;
  font-size: 12px;
}

.toolbar-actions {
  flex-shrink: 0;
}

.workspace-layout {
  margin-bottom: 8px;
}

.workspace-panel {
  min-height: 520px;
}

.panel-title {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.panel-subtitle {
  color: #8a94a6;
  font-size: 12px;
  font-weight: 400;
}

.selection-alert {
  margin-bottom: 16px;
}

.candidate-filter {
  margin-bottom: 8px;
}

.group-list,
.group-items,
.candidate-list,
.candidate-cards {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.group-section {
  background: #f8fafc;
  border: 1px solid #ebf0f5;
  border-radius: 18px;
  padding: 16px;
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.group-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
}

.group-score {
  color: #1f4e79;
  font-weight: 600;
}

.question-card {
  background: #fff;
  border: 1px solid #e6edf5;
  border-radius: 16px;
  padding: 16px;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.question-card.active {
  border-color: #1f4e79;
  box-shadow: 0 0 0 3px rgba(31, 78, 121, 0.12);
}

.question-card.dragging {
  opacity: 0.75;
}

.question-card.over {
  border-color: #3d8ed0;
}

.current-card {
  cursor: grab;
}

.candidate-card {
  cursor: pointer;
}

.card-topline,
.card-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.card-order {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #7a8798;
}

.candidate-batch-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid #e6edf5;
  border-radius: 14px;
  background: #f8fafc;
}

.candidate-batch-info {
  color: #4b5563;
  font-size: 13px;
  font-weight: 600;
}

.candidate-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.order-badge {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background: #1f4e79;
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  flex: 0 0 auto;
}

.drag-icon {
  color: #7a8798;
}

.drag-text,
.candidate-title-text {
  color: #7a8798;
  font-size: 12px;
}

.card-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.card-button {
  border-radius: 999px;
}

.score-editor {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #6b7280;
  font-size: 13px;
}

.card-stem {
  margin: 14px 0 12px;
  color: #111827;
  line-height: 1.8;
  white-space: pre-wrap;
}

.meta-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.group-dropzone {
  border: 1px dashed #c8d4e1;
  color: #8a94a6;
  border-radius: 14px;
  padding: 10px 12px;
  text-align: center;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.7);
}

.group-dropzone.active {
  border-color: #3d8ed0;
  background: #edf5fd;
  color: #1f4e79;
}

@media (max-width: 1200px) {
  .toolbar-main,
  .card-topline,
  .card-meta-row,
  .group-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .toolbar-actions,
  .card-controls {
    width: 100%;
  }
}
</style>
