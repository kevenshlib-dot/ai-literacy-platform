<template>
  <div class="paper-editor">
    <!-- Top Toolbar -->
    <div class="editor-toolbar">
      <div class="toolbar-left">
        <a-button @click="goBack">
          <template #icon><ArrowLeftOutlined /></template>
          返回试卷列表
        </a-button>
        <a-typography-title
          :level="4"
          :editable="{ onChange: onTitleChange }"
          :content="paper.title"
          style="margin: 0 0 0 16px"
        />
      </div>
      <div class="toolbar-center">
        <a-space :size="24">
          <span class="toolbar-stat">
            <FileTextOutlined /> {{ paperQuestions.length }} 题
          </span>
          <span class="toolbar-stat">
            <TrophyOutlined /> 总分 {{ totalScore }}
          </span>
          <span class="toolbar-stat">
            <ClockCircleOutlined /> {{ paper.time_limit_minutes ? paper.time_limit_minutes + ' 分钟' : '不限时' }}
          </span>
        </a-space>
      </div>
      <div class="toolbar-right">
        <a-space>
          <a-button type="primary" :loading="saving" @click="savePaper">
            <template #icon><SaveOutlined /></template>
            保存
          </a-button>
          <a-button @click="autoAssembleModal.visible = true">
            <template #icon><ThunderboltOutlined /></template>
            自动组卷
          </a-button>
        </a-space>
      </div>
    </div>

    <a-spin :spinning="loading" tip="加载中...">
      <div class="editor-body">
        <!-- Left Panel: Paper Structure -->
        <div class="panel-left">
          <div class="panel-header">
            <span class="panel-title">试卷结构</span>
            <a-button size="small" type="dashed" @click="addSection">
              <template #icon><PlusOutlined /></template>
              添加分节
            </a-button>
          </div>

          <a-empty v-if="sections.length === 0 && unsectionedQuestions.length === 0" description="暂无题目，请从右侧题库添加" />

          <!-- Sections -->
          <a-collapse v-model:activeKey="activeSections" class="section-collapse">
            <a-collapse-panel v-for="section in sections" :key="section.id" :forceRender="false">
              <template #header>
                <div class="section-header" @click.stop>
                  <a-typography-text
                    :editable="{ onChange: (val: string) => updateSectionTitle(section, val) }"
                    :content="section.title"
                    class="section-title-text"
                  />
                  <a-space class="section-meta">
                    <a-tag>{{ sectionQuestions(section.id).length }} 题</a-tag>
                    <a-tag color="blue">{{ sectionScore(section.id) }} 分</a-tag>
                  </a-space>
                </div>
              </template>
              <template #extra>
                <a-popconfirm title="确定删除此分节？分节内的题目将变为未分节。" @confirm.stop="deleteSection(section)">
                  <a-button size="small" danger type="text" @click.stop>
                    <template #icon><DeleteOutlined /></template>
                  </a-button>
                </a-popconfirm>
              </template>

              <!-- Questions in section -->
              <div v-if="sectionQuestions(section.id).length === 0" class="empty-section">
                <a-empty description="该分节暂无题目" :image="simpleImage" />
              </div>
              <div v-else class="question-list">
                <div
                  v-for="(pq, qi) in sectionQuestions(section.id)"
                  :key="pq.id"
                  class="question-row"
                >
                  <div class="question-order">{{ qi + 1 }}</div>
                  <a-select
                    :value="effectiveType(pq)"
                    size="small"
                    style="width: 80px"
                    @change="(val: string) => changeQuestionType(pq, val)"
                  >
                    <a-select-option v-for="opt in TYPE_OPTIONS" :key="opt.value" :value="opt.value">
                      {{ opt.label }}
                    </a-select-option>
                  </a-select>
                  <div class="question-stem" @click="toggleExpand(pq.id)">
                    {{ truncate(pq.stem || pq.stem_override || '', 60) }}
                  </div>
                  <a-input-number
                    v-model:value="pq.score"
                    :min="0"
                    :max="100"
                    size="small"
                    style="width: 70px"
                    @change="updateQuestionScore(pq)"
                  />
                  <span class="score-unit">分</span>
                  <a-space size="small">
                    <a-tooltip title="上移">
                      <a-button size="small" type="text" :disabled="qi === 0" @click="moveQuestion(section.id, qi, -1)">
                        <template #icon><UpOutlined /></template>
                      </a-button>
                    </a-tooltip>
                    <a-tooltip title="下移">
                      <a-button size="small" type="text" :disabled="qi === sectionQuestions(section.id).length - 1" @click="moveQuestion(section.id, qi, 1)">
                        <template #icon><DownOutlined /></template>
                      </a-button>
                    </a-tooltip>
                    <a-popconfirm title="移除该题目？" @confirm="removeQuestion(pq)">
                      <a-button size="small" type="text" danger>
                        <template #icon><CloseOutlined /></template>
                      </a-button>
                    </a-popconfirm>
                  </a-space>

                  <!-- Expandable override editing -->
                  <div v-if="expandedQuestion === pq.id" class="question-expand" @click.stop>
                    <a-form layout="vertical" size="small">
                      <a-form-item label="题干">
                        <a-textarea v-model:value="pq.stem_override" :rows="3" :placeholder="pq.stem || '留空则使用原题干'" @blur="updateQuestionOverride(pq)" />
                        <div v-if="pq.stem && pq.stem_override && pq.stem_override !== pq.stem" class="answer-hint">原题干: {{ pq.stem }}</div>
                      </a-form-item>
                      <template v-if="hasOptionsType(pq)">
                        <a-form-item label="选项">
                          <a-row :gutter="[8, 8]">
                            <a-col v-for="key in optionKeys(pq)" :key="key" :span="12">
                              <a-input
                                :addon-before="key"
                                v-model:value="pq.editOptions[key]"
                                size="small"
                                @blur="commitOptionsEdit(pq)"
                              />
                            </a-col>
                          </a-row>
                        </a-form-item>
                      </template>
                      <a-form-item label="正确答案">
                        <a-radio-group v-if="effectiveType(pq) === 'true_false'" v-model:value="pq.correct_answer_override" @change="updateCorrectAnswerOverride(pq)">
                          <a-radio value="T">T. 正确</a-radio>
                          <a-radio value="F">F. 错误</a-radio>
                        </a-radio-group>
                        <template v-else-if="effectiveType(pq) === 'single_choice'">
                          <a-radio-group v-model:value="pq.correct_answer_override" @change="updateCorrectAnswerOverride(pq)">
                            <a-radio v-for="key in optionKeys(pq)" :key="key" :value="key">{{ key }}</a-radio>
                          </a-radio-group>
                        </template>
                        <template v-else-if="effectiveType(pq) === 'multiple_choice'">
                          <a-checkbox-group v-model:value="pq.multiAnswerSelected" @change="onMultiAnswerChange(pq)">
                            <a-checkbox v-for="key in optionKeys(pq)" :key="key" :value="key">{{ key }}</a-checkbox>
                          </a-checkbox-group>
                        </template>
                        <a-input
                          v-else
                          v-model:value="pq.correct_answer_override"
                          placeholder="输入答案内容"
                          @blur="updateCorrectAnswerOverride(pq)"
                        />
                        <div class="answer-hint">原答案: {{ pq.correct_answer || '（无）' }}</div>
                      </a-form-item>
                    </a-form>
                  </div>
                </div>
              </div>
            </a-collapse-panel>
          </a-collapse>

          <!-- Unsectioned Questions -->
          <div v-if="unsectionedQuestions.length > 0" class="unsectioned-block">
            <div class="unsectioned-header">
              <span>未分节题目</span>
              <a-space class="section-meta">
                <a-tag>{{ unsectionedQuestions.length }} 题</a-tag>
                <a-tag color="blue">{{ unsectionedScore }} 分</a-tag>
              </a-space>
            </div>
            <div class="question-list">
              <div
                v-for="(pq, qi) in unsectionedQuestions"
                :key="pq.id"
                class="question-row"
              >
                <div class="question-order">{{ qi + 1 }}</div>
                <a-select
                  :value="effectiveType(pq)"
                  size="small"
                  style="width: 80px"
                  @change="(val: string) => changeQuestionType(pq, val)"
                >
                  <a-select-option v-for="opt in TYPE_OPTIONS" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </a-select-option>
                </a-select>
                <div class="question-stem" @click="toggleExpand(pq.id)">
                  {{ truncate(pq.stem || pq.stem_override || '', 60) }}
                </div>
                <a-input-number
                  v-model:value="pq.score"
                  :min="0"
                  :max="100"
                  size="small"
                  style="width: 70px"
                  @change="updateQuestionScore(pq)"
                />
                <span class="score-unit">分</span>
                <a-space size="small">
                  <a-tooltip title="上移">
                    <a-button size="small" type="text" :disabled="qi === 0" @click="moveQuestion(null, qi, -1)">
                      <template #icon><UpOutlined /></template>
                    </a-button>
                  </a-tooltip>
                  <a-tooltip title="下移">
                    <a-button size="small" type="text" :disabled="qi === unsectionedQuestions.length - 1" @click="moveQuestion(null, qi, 1)">
                      <template #icon><DownOutlined /></template>
                    </a-button>
                  </a-tooltip>
                  <a-popconfirm title="移除该题目？" @confirm="removeQuestion(pq)">
                    <a-button size="small" type="text" danger>
                      <template #icon><CloseOutlined /></template>
                    </a-button>
                  </a-popconfirm>
                </a-space>

                <div v-if="expandedQuestion === pq.id" class="question-expand" @click.stop>
                  <a-form layout="vertical" size="small">
                    <a-form-item label="题干">
                      <a-textarea v-model:value="pq.stem_override" :rows="3" :placeholder="pq.stem || '留空则使用原题干'" @blur="updateQuestionOverride(pq)" />
                      <div v-if="pq.stem && pq.stem_override && pq.stem_override !== pq.stem" class="answer-hint">原题干: {{ pq.stem }}</div>
                    </a-form-item>
                    <template v-if="hasOptionsType(pq)">
                      <a-form-item label="选项">
                        <a-row :gutter="[8, 8]">
                          <a-col v-for="key in optionKeys(pq)" :key="key" :span="12">
                            <a-input
                              :addon-before="key"
                              v-model:value="pq.editOptions[key]"
                              size="small"
                              @blur="commitOptionsEdit(pq)"
                            />
                          </a-col>
                        </a-row>
                      </a-form-item>
                    </template>
                    <a-form-item label="正确答案">
                      <a-radio-group v-if="effectiveType(pq) === 'true_false'" v-model:value="pq.correct_answer_override" @change="updateCorrectAnswerOverride(pq)">
                        <a-radio value="A">A. 正确</a-radio>
                        <a-radio value="B">B. 错误</a-radio>
                      </a-radio-group>
                      <template v-else-if="effectiveType(pq) === 'single_choice'">
                        <a-radio-group v-model:value="pq.correct_answer_override" @change="updateCorrectAnswerOverride(pq)">
                          <a-radio v-for="key in optionKeys(pq)" :key="key" :value="key">{{ key }}</a-radio>
                        </a-radio-group>
                      </template>
                      <template v-else-if="effectiveType(pq) === 'multiple_choice'">
                        <a-checkbox-group v-model:value="pq.multiAnswerSelected" @change="onMultiAnswerChange(pq)">
                          <a-checkbox v-for="key in optionKeys(pq)" :key="key" :value="key">{{ key }}</a-checkbox>
                        </a-checkbox-group>
                      </template>
                      <a-input
                        v-else
                        v-model:value="pq.correct_answer_override"
                        placeholder="输入答案内容"
                        @blur="updateCorrectAnswerOverride(pq)"
                      />
                      <div class="answer-hint">原答案: {{ pq.correct_answer || '（无）' }}</div>
                    </a-form-item>
                  </a-form>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Right Panel: Question Bank Browser -->
        <div class="panel-right">
          <div class="panel-header">
            <span class="panel-title">题库浏览</span>
          </div>

          <!-- Filters -->
          <div class="bank-filters">
            <a-input
              v-model:value="bankFilters.keyword"
              placeholder="搜索题干关键词"
              allow-clear
              size="small"
              @press-enter="fetchBankQuestions"
            >
              <template #prefix><SearchOutlined /></template>
            </a-input>
            <a-row :gutter="8" style="margin-top: 8px">
              <a-col :span="12">
                <a-select v-model:value="bankFilters.question_type" placeholder="题型" allow-clear size="small" style="width: 100%" @change="fetchBankQuestions">
                  <a-select-option value="single_choice">单选题</a-select-option>
                  <a-select-option value="multiple_choice">多选题</a-select-option>
                  <a-select-option value="true_false">判断题</a-select-option>
                  <a-select-option value="fill_blank">填空题</a-select-option>
                  <a-select-option value="short_answer">简答题</a-select-option>
                  <a-select-option value="essay">论述题</a-select-option>
                </a-select>
              </a-col>
              <a-col :span="12">
                <a-select v-model:value="bankFilters.difficulty" placeholder="难度" allow-clear size="small" style="width: 100%" @change="fetchBankQuestions">
                  <a-select-option :value="1">1 - 入门</a-select-option>
                  <a-select-option :value="2">2 - 简单</a-select-option>
                  <a-select-option :value="3">3 - 中等</a-select-option>
                  <a-select-option :value="4">4 - 困难</a-select-option>
                  <a-select-option :value="5">5 - 专家</a-select-option>
                </a-select>
              </a-col>
            </a-row>
          </div>

          <!-- Question Bank List -->
          <a-spin :spinning="bankLoading">
            <div class="bank-list">
              <a-empty v-if="bankQuestions.length === 0" description="无匹配题目" />
              <div
                v-for="q in bankQuestions"
                :key="q.id"
                class="bank-card"
                :class="{ dimmed: isInPaper(q.id) }"
              >
                <div class="bank-card-top">
                  <a-tag :color="typeColor(q.question_type)" size="small">{{ typeLabel(q.question_type) }}</a-tag>
                  <span class="bank-difficulty">
                    <StarFilled v-for="s in (q.difficulty || 1)" :key="s" style="color: #faad14; font-size: 12px" />
                    <StarOutlined v-for="s in (5 - (q.difficulty || 1))" :key="'e' + s" style="color: #d9d9d9; font-size: 12px" />
                  </span>
                </div>
                <div class="bank-card-stem">{{ truncate(q.stem, 80) }}</div>
                <div class="bank-card-actions">
                  <a-button
                    size="small"
                    type="primary"
                    :disabled="isInPaper(q.id)"
                    @click="addQuestionToPaper(q)"
                  >
                    {{ isInPaper(q.id) ? '已添加' : '添加' }}
                  </a-button>
                </div>
              </div>
            </div>
          </a-spin>

          <div class="bank-pagination">
            <a-pagination
              v-model:current="bankPagination.current"
              :page-size="bankPagination.pageSize"
              :total="bankPagination.total"
              size="small"
              show-less-items
              @change="onBankPageChange"
            />
          </div>
        </div>
      </div>
    </a-spin>

    <!-- Auto-Assemble Modal -->
    <a-modal
      v-model:open="autoAssembleModal.visible"
      title="自动组卷"
      width="680px"
      :confirm-loading="autoAssembleModal.loading"
      @ok="handleAutoAssemble"
    >
      <a-form layout="vertical">
        <a-form-item label="组卷规则">
          <div v-for="(rule, ri) in autoAssembleModal.rules" :key="ri" class="assemble-rule-row">
            <a-row :gutter="8" align="middle">
              <a-col :span="5">
                <a-select v-model:value="rule.question_type" placeholder="题型" size="small" style="width: 100%">
                  <a-select-option value="single_choice">单选题</a-select-option>
                  <a-select-option value="multiple_choice">多选题</a-select-option>
                  <a-select-option value="true_false">判断题</a-select-option>
                  <a-select-option value="fill_blank">填空题</a-select-option>
                  <a-select-option value="short_answer">简答题</a-select-option>
                  <a-select-option value="essay">论述题</a-select-option>
                </a-select>
              </a-col>
              <a-col :span="4">
                <a-input-number v-model:value="rule.count" :min="1" :max="50" placeholder="数量" size="small" style="width: 100%" />
              </a-col>
              <a-col :span="4">
                <a-input-number v-model:value="rule.score_per_question" :min="1" :max="100" placeholder="每题分" size="small" style="width: 100%" />
              </a-col>
              <a-col :span="4">
                <a-select v-model:value="rule.difficulty" placeholder="难度" allow-clear size="small" style="width: 100%">
                  <a-select-option :value="1">1</a-select-option>
                  <a-select-option :value="2">2</a-select-option>
                  <a-select-option :value="3">3</a-select-option>
                  <a-select-option :value="4">4</a-select-option>
                  <a-select-option :value="5">5</a-select-option>
                </a-select>
              </a-col>
              <a-col :span="5">
                <a-input v-model:value="rule.dimension" placeholder="维度(可选)" size="small" />
              </a-col>
              <a-col :span="2">
                <a-button size="small" type="text" danger @click="autoAssembleModal.rules.splice(ri, 1)" :disabled="autoAssembleModal.rules.length <= 1">
                  <template #icon><DeleteOutlined /></template>
                </a-button>
              </a-col>
            </a-row>
          </div>
          <a-button type="dashed" size="small" block style="margin-top: 8px" @click="addAssembleRule">
            <template #icon><PlusOutlined /></template>
            添加规则
          </a-button>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { Empty } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  PlusOutlined,
  DeleteOutlined,
  CloseOutlined,
  UpOutlined,
  DownOutlined,
  SearchOutlined,
  SaveOutlined,
  ThunderboltOutlined,
  FileTextOutlined,
  TrophyOutlined,
  ClockCircleOutlined,
  StarFilled,
  StarOutlined,
} from '@ant-design/icons-vue'
import request from '@/utils/request'

const route = useRoute()
const router = useRouter()
const paperId = computed(() => route.params.id as string)
const simpleImage = Empty.PRESENTED_IMAGE_SIMPLE

// ── State ─────────────────────────────────────────────────────────────────────
const loading = ref(false)
const saving = ref(false)

const paper = reactive({
  title: '',
  description: '',
  total_score: 0,
  time_limit_minutes: null as number | null,
  status: 'draft',
})

interface PaperQuestion {
  id: string
  question_id: string
  section_id: string | null
  score: number
  order_num: number
  question_type: string
  question_type_override: string | null
  correct_answer: string
  correct_answer_override: string | null
  stem: string
  stem_override: string | null
  options: any | null
  options_override: any | null
  options_override_str: string
  // Parsed editable options for UI (merged override or original)
  editOptions: Record<string, string>
  // For multiple_choice answer editing
  multiAnswerSelected: string[]
}

interface Section {
  id: string
  title: string
  order_num: number
}

const sections = ref<Section[]>([])
const paperQuestions = ref<PaperQuestion[]>([])
const activeSections = ref<string[]>([])
const expandedQuestion = ref<string | null>(null)

// ── Question type helpers ─────────────────────────────────────────────────────
const TYPE_MAP: Record<string, { label: string; color: string }> = {
  single_choice:   { label: '单选', color: 'blue' },
  multiple_choice: { label: '多选', color: 'purple' },
  true_false:      { label: '判断', color: 'geekblue' },
  fill_blank:      { label: '填空', color: 'cyan' },
  short_answer:    { label: '简答', color: 'orange' },
  essay:           { label: '论述', color: 'red' },
}

const TYPE_OPTIONS = Object.entries(TYPE_MAP).map(([value, { label }]) => ({ value, label }))

function typeLabel(t: string) { return TYPE_MAP[t]?.label ?? t }
function typeColor(t: string) { return TYPE_MAP[t]?.color ?? 'default' }
function effectiveType(pq: PaperQuestion) { return pq.question_type_override || pq.question_type }
function truncate(s: string, len: number) {
  if (!s) return ''
  return s.length > len ? s.slice(0, len) + '...' : s
}

// ── Computed ──────────────────────────────────────────────────────────────────
const totalScore = computed(() => paperQuestions.value.reduce((sum, q) => sum + (q.score || 0), 0))

function sectionQuestions(sectionId: string): PaperQuestion[] {
  return paperQuestions.value
    .filter(q => q.section_id === sectionId)
    .sort((a, b) => a.order_num - b.order_num)
}

function sectionScore(sectionId: string): number {
  return sectionQuestions(sectionId).reduce((sum, q) => sum + (q.score || 0), 0)
}

const unsectionedQuestions = computed(() =>
  paperQuestions.value
    .filter(q => !q.section_id)
    .sort((a, b) => a.order_num - b.order_num)
)

const unsectionedScore = computed(() =>
  unsectionedQuestions.value.reduce((sum, q) => sum + (q.score || 0), 0)
)

// ── Track which question_ids are in the paper ─────────────────────────────────
const paperQuestionIds = computed(() => new Set(paperQuestions.value.map(q => q.question_id)))
function isInPaper(questionId: string) { return paperQuestionIds.value.has(questionId) }

// ── Load paper ────────────────────────────────────────────────────────────────
async function loadPaper() {
  loading.value = true
  try {
    const data: any = await request.get(`/papers/${paperId.value}`)
    paper.title = data.title || ''
    paper.description = data.description || ''
    paper.total_score = data.total_score || 0
    paper.time_limit_minutes = data.time_limit_minutes
    paper.status = data.status || 'draft'

    // Sections
    sections.value = (data.sections || []).map((s: any) => ({
      id: s.id,
      title: s.title,
      order_num: s.order_num ?? 0,
    }))
    sections.value.sort((a, b) => a.order_num - b.order_num)
    activeSections.value = sections.value.map(s => s.id)

    // Flatten questions from sections + unsectioned_questions
    const allQuestions: any[] = []
    for (const sec of (data.sections || [])) {
      for (const q of (sec.questions || [])) {
        allQuestions.push({ ...q, section_id: sec.id })
      }
    }
    for (const q of (data.unsectioned_questions || [])) {
      allQuestions.push({ ...q, section_id: null })
    }

    paperQuestions.value = allQuestions.map((q: any) => {
      const origOptions = q.question?.options || null
      const overrideOptions = q.options_override || null
      const mergedOptions: Record<string, string> = { ...(origOptions || {}), ...(overrideOptions || {}) }
      const effectiveAnswer = q.correct_answer_override || q.question?.correct_answer || ''
      const qtype = q.question_type_override || q.question?.question_type || ''
      return {
        id: q.id,
        question_id: q.question_id,
        section_id: q.section_id || null,
        score: q.score ?? 0,
        order_num: q.order_num ?? 0,
        question_type: q.question?.question_type || '',
        question_type_override: q.question_type_override || null,
        correct_answer: q.question?.correct_answer || '',
        correct_answer_override: q.correct_answer_override || null,
        stem: q.question?.stem || '',
        stem_override: q.stem_override || null,
        options: origOptions,
        options_override: overrideOptions,
        options_override_str: overrideOptions ? JSON.stringify(overrideOptions) : '',
        editOptions: mergedOptions,
        multiAnswerSelected: qtype === 'multiple_choice'
          ? effectiveAnswer.split('').filter((c: string) => /[A-Z]/i.test(c)).map((c: string) => c.toUpperCase())
          : [],
      }
    })
  } catch { /* handled by interceptor */ }
  finally { loading.value = false }
}

// ── Save paper metadata ───────────────────────────────────────────────────────
async function savePaper() {
  saving.value = true
  try {
    await request.put(`/papers/${paperId.value}`, {
      title: paper.title,
      description: paper.description,
      total_score: totalScore.value,
      time_limit_minutes: paper.time_limit_minutes,
    })
    message.success('保存成功')
  } catch { /* handled */ }
  finally { saving.value = false }
}

function onTitleChange(val: string) {
  paper.title = val
}

function goBack() {
  router.push('/papers')
}

// ── Sections ──────────────────────────────────────────────────────────────────
async function addSection() {
  try {
    const data: any = await request.post(`/papers/${paperId.value}/sections`, {
      title: `第 ${sections.value.length + 1} 节`,
    })
    sections.value.push({
      id: data.id,
      title: data.title,
      order_num: data.order_num ?? sections.value.length,
    })
    activeSections.value.push(data.id)
    message.success('分节已添加')
  } catch { /* handled */ }
}

async function updateSectionTitle(section: Section, val: string) {
  section.title = val
  try {
    await request.put(`/papers/sections/${section.id}`, {
      title: val,
    })
  } catch { /* handled */ }
}

async function deleteSection(section: Section) {
  try {
    await request.delete(`/papers/sections/${section.id}`)
    sections.value = sections.value.filter(s => s.id !== section.id)
    // Move questions to unsectioned
    paperQuestions.value.forEach(q => {
      if (q.section_id === section.id) q.section_id = null
    })
    message.success('分节已删除')
  } catch { /* handled */ }
}

// ── Question operations ───────────────────────────────────────────────────────
function toggleExpand(pqId: string) {
  expandedQuestion.value = expandedQuestion.value === pqId ? null : pqId
}

async function updateQuestionScore(pq: PaperQuestion) {
  try {
    await request.put(`/papers/questions/${pq.id}`, {
      score: pq.score,
    })
  } catch { /* handled */ }
}

const OBJECTIVE_TYPES = new Set(['single_choice', 'multiple_choice', 'true_false'])
const OPTIONS_TYPES = new Set(['single_choice', 'multiple_choice'])

function hasOptionsType(pq: PaperQuestion): boolean {
  return OPTIONS_TYPES.has(effectiveType(pq))
}

function optionKeys(pq: PaperQuestion): string[] {
  const merged = { ...(pq.options || {}), ...(pq.editOptions || {}) }
  const keys = Object.keys(merged).filter(k => k.length === 1 && /[A-Z]/i.test(k))
  if (keys.length === 0) return ['A', 'B', 'C', 'D']
  return keys.sort()
}

async function commitOptionsEdit(pq: PaperQuestion) {
  // Build the override from editOptions — only include non-empty entries
  const override: Record<string, string> = {}
  for (const [k, v] of Object.entries(pq.editOptions)) {
    if (v && v.trim()) override[k] = v.trim()
  }
  pq.options_override = Object.keys(override).length > 0 ? override : null
  pq.options_override_str = pq.options_override ? JSON.stringify(pq.options_override) : ''
  try {
    await request.put(`/papers/questions/${pq.id}`, {
      options_override: pq.options_override,
    })
    message.success('选项已保存')
  } catch { /* handled */ }
}

function onMultiAnswerChange(pq: PaperQuestion) {
  pq.correct_answer_override = pq.multiAnswerSelected.sort().join('')
  updateCorrectAnswerOverride(pq)
}

async function changeQuestionType(pq: PaperQuestion, newType: string) {
  const override = newType === pq.question_type ? null : newType
  pq.question_type_override = override
  // If changing to true_false, try to auto-detect correct answer from stem
  if (override === 'true_false' && !pq.correct_answer_override) {
    const stem = (pq.stem || '').trim()
    // Simple heuristic: if stem contains clear true/false indicator, auto-fill
    if (stem.endsWith('（×）') || stem.endsWith('(×)') || stem.endsWith('（错）') || stem.endsWith('(F)')) {
      pq.correct_answer_override = 'B'
    } else if (stem.endsWith('（√）') || stem.endsWith('(√)') || stem.endsWith('（对）') || stem.endsWith('(T)')) {
      pq.correct_answer_override = 'A'
    }
  }
  // If reverting to original type, clear the answer override too
  if (!override) {
    pq.correct_answer_override = null
  }
  // Sync multiAnswerSelected when switching to multiple_choice
  if (override === 'multiple_choice' || pq.question_type === 'multiple_choice') {
    const answer = pq.correct_answer_override || pq.correct_answer || ''
    pq.multiAnswerSelected = answer.split('').filter((c: string) => /[A-Z]/i.test(c)).map((c: string) => c.toUpperCase())
  } else {
    pq.multiAnswerSelected = []
  }
  try {
    await request.put(`/papers/questions/${pq.id}`, {
      question_type_override: override,
      correct_answer_override: pq.correct_answer_override,
    })
    message.success('题型已修改')
    // Auto-expand to show answer setting
    if (override && OBJECTIVE_TYPES.has(override)) {
      expandedQuestion.value = pq.id
    }
  } catch { /* handled */ }
}

async function updateCorrectAnswerOverride(pq: PaperQuestion) {
  try {
    await request.put(`/papers/questions/${pq.id}`, {
      correct_answer_override: pq.correct_answer_override || null,
    })
    message.success('正确答案已保存')
  } catch { /* handled */ }
}

async function updateQuestionOverride(pq: PaperQuestion) {
  try {
    await request.put(`/papers/questions/${pq.id}`, {
      stem_override: pq.stem_override || null,
    })
    message.success('题干已保存')
  } catch { /* handled */ }
}

async function removeQuestion(pq: PaperQuestion) {
  try {
    await request.delete(`/papers/questions/${pq.id}`)
    paperQuestions.value = paperQuestions.value.filter(q => q.id !== pq.id)
    message.success('已移除')
  } catch { /* handled */ }
}

async function moveQuestion(sectionId: string | null, index: number, direction: -1 | 1) {
  const list = sectionId
    ? sectionQuestions(sectionId)
    : unsectionedQuestions.value
  const targetIndex = index + direction
  if (targetIndex < 0 || targetIndex >= list.length) return
  const currentQuestion = list[index]
  const targetQuestion = list[targetIndex]
  if (!currentQuestion || !targetQuestion) return

  // Swap order_num
  const temp = currentQuestion.order_num
  currentQuestion.order_num = targetQuestion.order_num
  targetQuestion.order_num = temp

  // Build ordered IDs for the full paper
  const allOrdered = [...paperQuestions.value]
    .sort((a, b) => a.order_num - b.order_num)
    .map(q => q.id)

  try {
    await request.post(`/papers/${paperId.value}/questions/reorder`, {
      ordered_ids: allOrdered,
    })
  } catch { /* handled */ }
}

// ── Add question from bank ────────────────────────────────────────────────────
async function addQuestionToPaper(q: any) {
  try {
    const lastSection = sections.value.length > 0 ? sections.value[sections.value.length - 1] : null
    const activeSectionId = lastSection ? lastSection.id : null
    await request.post(`/papers/${paperId.value}/questions`, [
      {
        question_id: q.id,
        section_id: activeSectionId,
        score: 5,
      },
    ])
    // Reload to get fresh data
    await loadPaper()
    message.success('题目已添加')
  } catch { /* handled */ }
}

// ── Question Bank Browser ─────────────────────────────────────────────────────
const bankLoading = ref(false)
const bankQuestions = ref<any[]>([])
const bankFilters = reactive({
  keyword: '',
  question_type: undefined as string | undefined,
  difficulty: undefined as number | undefined,
})
const bankPagination = reactive({ current: 1, pageSize: 20, total: 0 })

async function fetchBankQuestions() {
  bankLoading.value = true
  try {
    const params: any = {
      skip: (bankPagination.current - 1) * bankPagination.pageSize,
      limit: bankPagination.pageSize,
      status: 'approved',
    }
    if (bankFilters.keyword) params.keyword = bankFilters.keyword
    if (bankFilters.question_type) params.question_type = bankFilters.question_type
    if (bankFilters.difficulty) params.difficulty = bankFilters.difficulty

    const data: any = await request.get('/questions', { params })
    bankQuestions.value = data.items || []
    bankPagination.total = data.total || 0
  } catch { /* handled */ }
  finally { bankLoading.value = false }
}

function onBankPageChange(page: number) {
  bankPagination.current = page
  fetchBankQuestions()
}

// ── Auto-Assemble Modal ──────────────────────────────────────────────────────
interface AssembleRule {
  question_type: string
  count: number
  score_per_question: number
  difficulty: number | undefined
  dimension: string
}

const autoAssembleModal = reactive({
  visible: false,
  loading: false,
  rules: [
    { question_type: 'single_choice', count: 10, score_per_question: 5, difficulty: undefined, dimension: '' },
  ] as AssembleRule[],
})

function addAssembleRule() {
  autoAssembleModal.rules.push({
    question_type: 'single_choice',
    count: 5,
    score_per_question: 5,
    difficulty: undefined,
    dimension: '',
  })
}

async function handleAutoAssemble() {
  const rules = autoAssembleModal.rules.filter(r => r.question_type && r.count > 0)
  if (rules.length === 0) {
    message.warning('请至少添加一条有效规则')
    return
  }
  autoAssembleModal.loading = true
  try {
    const payload = {
      rules: rules.map(r => {
        const rule: any = {
          question_type: r.question_type,
          count: r.count,
          score_per_question: r.score_per_question,
        }
        if (r.difficulty) rule.difficulty = r.difficulty
        if (r.dimension) rule.dimension = r.dimension
        return rule
      }),
    }
    const data: any = await request.post(`/papers/${paperId.value}/auto-assemble`, payload)
    message.success(`自动组卷完成，共添加 ${data.total_questions ?? ''} 题`)
    autoAssembleModal.visible = false
    await loadPaper()
  } catch { /* handled */ }
  finally { autoAssembleModal.loading = false }
}

// ── Init ──────────────────────────────────────────────────────────────────────
onMounted(() => {
  loadPaper()
  fetchBankQuestions()
})
</script>

<style scoped>
.paper-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

/* Toolbar */
.editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}
.toolbar-left {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
}
.toolbar-center {
  flex-shrink: 0;
  padding: 0 24px;
}
.toolbar-stat {
  font-size: 13px;
  color: #666;
  white-space: nowrap;
}
.toolbar-right {
  flex-shrink: 0;
}

/* Body */
.editor-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* Left panel */
.panel-left {
  width: 60%;
  border-right: 1px solid #f0f0f0;
  padding: 16px;
  overflow-y: auto;
  background: #fafafa;
}

/* Right panel */
.panel-right {
  width: 40%;
  padding: 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.panel-title {
  font-size: 15px;
  font-weight: 600;
}

/* Section collapse */
.section-collapse {
  background: transparent;
}
.section-collapse :deep(.ant-collapse-item) {
  margin-bottom: 8px;
  background: #fff;
  border-radius: 6px !important;
  border: 1px solid #e8e8e8;
}
.section-collapse :deep(.ant-collapse-content) {
  border-top: 1px solid #f0f0f0;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}
.section-title-text {
  font-weight: 600;
  font-size: 14px;
}
.section-meta {
  margin-left: auto;
}

.empty-section {
  padding: 16px;
}

/* Question rows */
.question-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}
.question-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  padding: 8px 12px;
  border-bottom: 1px solid #f5f5f5;
  gap: 8px;
}
.question-row:last-child {
  border-bottom: none;
}
.question-order {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  flex-shrink: 0;
}
.question-stem {
  flex: 1;
  font-size: 13px;
  color: #333;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.question-stem:hover {
  color: #1677ff;
}
.score-unit {
  font-size: 12px;
  color: #999;
}

.question-expand {
  width: 100%;
  padding: 12px 0 4px;
  border-top: 1px dashed #e8e8e8;
  margin-top: 4px;
}

.answer-hint {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

/* Unsectioned block */
.unsectioned-block {
  margin-top: 12px;
  background: #fff;
  border: 1px dashed #d9d9d9;
  border-radius: 6px;
  padding: 12px;
}
.unsectioned-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-weight: 600;
  font-size: 14px;
  color: #666;
}

/* Bank filters */
.bank-filters {
  margin-bottom: 12px;
}

/* Bank list */
.bank-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}
.bank-card {
  padding: 10px 12px;
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  transition: box-shadow 0.2s;
}
.bank-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.bank-card.dimmed {
  opacity: 0.45;
  pointer-events: none;
}
.bank-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.bank-difficulty {
  display: flex;
  gap: 2px;
}
.bank-card-stem {
  font-size: 13px;
  color: #333;
  margin-bottom: 8px;
  line-height: 1.5;
}
.bank-card-actions {
  text-align: right;
}

.bank-pagination {
  flex-shrink: 0;
  text-align: center;
  padding-top: 8px;
  border-top: 1px solid #f0f0f0;
}

/* Assemble modal */
.assemble-rule-row {
  margin-bottom: 8px;
}
</style>
