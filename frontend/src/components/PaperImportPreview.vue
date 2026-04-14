<template>
  <div class="paper-import-preview">
    <!-- Header -->
    <div style="margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between">
      <div>
        <a-tag v-if="llmEnhanced" color="green">AI 已分析</a-tag>
        <a-tag v-else color="default">仅规则解析</a-tag>
        <span style="font-size: 16px; font-weight: 600; margin-left: 8px">{{ paperTitle }}</span>
        <span style="margin-left: 12px; color: #666">共 {{ totalQuestions }} 题</span>
      </div>
      <div>
        <a-badge :count="issueCount" :offset="[6, -2]" style="margin-right: 12px">
          <a-button size="small" @click="jumpToNextIssue" :disabled="issueCount === 0">
            跳转下一问题
          </a-button>
        </a-badge>
        <a-button size="small" @click="acceptAllLLM" :disabled="!llmEnhanced" style="margin-right: 8px">
          全部采纳 AI 建议
        </a-button>
      </div>
    </div>

    <!-- Issue summary -->
    <a-alert
      v-if="issueCount > 0"
      :message="`发现 ${issueCount} 处问题需要确认（红色=缺答案，黄色=需检查）`"
      type="warning"
      show-icon
      style="margin-bottom: 16px"
    />

    <!-- Section-based question cards -->
    <template v-for="(sec, si) in sections" :key="si">
      <a-collapse v-model:activeKey="sectionKeys" style="margin-bottom: 12px">
        <a-collapse-panel :key="String(si)" :header="`${sec.title || '未分组'} (${sec.questions.length} 题)`">
          <div
            v-for="q in sec.questions"
            :key="q.order_num"
            :id="`q-${q.order_num}`"
            :class="['question-card', getCardClass(q)]"
          >
            <!-- Question header row -->
            <div class="q-header">
              <span class="q-num">第 {{ q.order_num }} 题</span>
              <a-select
                :value="getEffectiveType(q)"
                size="small"
                style="width: 110px"
                @change="(v: string) => onTypeChange(q, v)"
              >
                <a-select-option v-for="t in typeOptions" :key="t.value" :value="t.value">
                  {{ t.label }}
                </a-select-option>
              </a-select>
              <span style="margin-left: 8px; color: #999; font-size: 12px">
                分值:
              </span>
              <a-input-number
                :value="q.score || 5"
                size="small"
                :min="0" :max="100" :step="1"
                style="width: 65px"
                @change="(v: number) => q.score = v"
              />
              <template v-if="llmEnhanced">
                <a-tag :color="getConfidenceColor(q.type_confidence || 0)" style="margin-left: 8px">
                  型 {{ Math.round((q.type_confidence || 0) * 100) }}%
                </a-tag>
                <a-tag :color="getConfidenceColor(q.answer_confidence || 0)">
                  答 {{ Math.round((q.answer_confidence || 0) * 100) }}%
                </a-tag>
              </template>
              <a-tag v-if="getStatus(q) === 'ok'" color="green" style="margin-left: auto">OK</a-tag>
              <a-tag v-else-if="getStatus(q) === 'warn'" color="orange" style="margin-left: auto">需确认</a-tag>
              <a-tag v-else color="red" style="margin-left: auto">缺答案</a-tag>
            </div>

            <!-- Issues alert -->
            <a-alert
              v-if="q.issues && q.issues.length"
              type="warning"
              size="small"
              style="margin-bottom: 8px"
            >
              <template #message>
                <span v-for="(issue, ii) in q.issues" :key="ii" style="font-size: 12px">
                  {{ issue }}<br v-if="Number(ii) < q.issues.length - 1" />
                </span>
              </template>
            </a-alert>

            <!-- Stem (editable) -->
            <div class="q-field">
              <label>题干</label>
              <a-textarea
                :value="getFullStem(q)"
                :autoSize="{ minRows: 2, maxRows: 8 }"
                @change="(e: any) => onStemChange(q, e.target.value)"
              />
            </div>

            <!-- Options (for choice / T-F types) -->
            <div v-if="hasOptions(q)" class="q-field">
              <label>选项</label>
              <div class="options-list">
                <div v-for="(val, key) in getOptionsOrDefault(q)" :key="key" class="option-row">
                  <span class="option-key">{{ key }}.</span>
                  <a-input
                    :value="val"
                    size="small"
                    @change="(e: any) => onOptionChange(q, String(key), e.target.value)"
                  />
                </div>
              </div>
            </div>

            <!-- Answer (editable, type-aware) -->
            <div class="q-field">
              <label>
                参考答案
                <a-button
                  v-if="llmEnhanced && q.llm_correct_answer && q.llm_correct_answer !== getEffectiveAnswer(q)"
                  type="link"
                  size="small"
                  @click="acceptLLMSuggestion(q)"
                  style="padding: 0; font-size: 12px"
                >
                  采纳 AI 建议 ({{ q.llm_correct_answer }})
                </a-button>
              </label>
              <!-- T/F: radio -->
              <a-radio-group
                v-if="getEffectiveType(q) === 'true_false'"
                :value="getEffectiveAnswer(q)"
                @change="(e: any) => onAnswerChange(q, e.target.value)"
              >
                <a-radio value="T">T (正确)</a-radio>
                <a-radio value="F">F (错误)</a-radio>
              </a-radio-group>
              <!-- Single choice: radio -->
              <a-radio-group
                v-else-if="getEffectiveType(q) === 'single_choice'"
                :value="getEffectiveAnswer(q)"
                @change="(e: any) => onAnswerChange(q, e.target.value)"
              >
                <a-radio v-for="key in getOptionKeys(q)" :key="key" :value="key">{{ key }}</a-radio>
              </a-radio-group>
              <!-- Multiple choice: checkbox -->
              <a-checkbox-group
                v-else-if="getEffectiveType(q) === 'multiple_choice'"
                :value="getEffectiveAnswer(q).split('')"
                @change="(vals: string[]) => onAnswerChange(q, vals.sort().join(''))"
              >
                <a-checkbox v-for="key in getOptionKeys(q)" :key="key" :value="key">{{ key }}</a-checkbox>
              </a-checkbox-group>
              <!-- Other types: text input -->
              <a-textarea
                v-else
                :value="getEffectiveAnswer(q)"
                :autoSize="{ minRows: 1, maxRows: 4 }"
                :placeholder="getAnswerPlaceholder(q)"
                @change="(e: any) => onAnswerChange(q, e.target.value)"
              />
            </div>

            <!-- Explanation (if any) -->
            <div v-if="q.question?.explanation" class="q-field">
              <label>解析</label>
              <a-textarea
                :value="q.question.explanation"
                :autoSize="{ minRows: 1, maxRows: 4 }"
                @change="(e: any) => { if (q.question) q.question.explanation = e.target.value }"
              />
            </div>
          </div>
        </a-collapse-panel>
      </a-collapse>
    </template>

    <!-- Footer -->
    <div style="margin-top: 16px; text-align: right; position: sticky; bottom: 0; background: #fff; padding: 12px 0; border-top: 1px solid #f0f0f0">
      <a-button style="margin-right: 8px" @click="$emit('cancel')">取消</a-button>
      <a-button type="primary" :loading="importing" @click="handleConfirmImport">
        确认导入 ({{ totalQuestions }} 题)
      </a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { message } from 'ant-design-vue'
import request from '@/utils/request'

interface Props {
  previewData: any
}

const props = defineProps<Props>()
const emit = defineEmits<{
  cancel: []
  imported: [paper: any]
}>()

const importing = ref(false)
const sectionKeys = ref<string[]>(['0'])

const llmEnhanced = computed(() => props.previewData?.llm_enhanced ?? false)
const paperTitle = computed(() => props.previewData?.title || '未命名试卷')

const parsedData = computed(() => props.previewData?.parsed_data || {})
const paperData = computed(() => parsedData.value?.paper || {})

// Build flat sections list (sections + unsectioned)
const sections = computed(() => {
  const result: any[] = []
  for (const sec of paperData.value.sections || []) {
    result.push({
      title: sec.title || '未命名分节',
      questions: (sec.questions || []).map((q: any) => reactive({ ...q })),
    })
  }
  const unsectioned = paperData.value.unsectioned_questions || []
  if (unsectioned.length > 0) {
    result.push({
      title: '未分组题目',
      questions: unsectioned.map((q: any) => reactive({ ...q })),
    })
  }
  sectionKeys.value = result.map((_, i) => String(i))
  return result
})

const totalQuestions = computed(() =>
  sections.value.reduce((sum, sec) => sum + sec.questions.length, 0)
)

const issueCount = computed(() => {
  let count = 0
  for (const sec of sections.value) {
    for (const q of sec.questions) {
      if (getStatus(q) !== 'ok') count++
    }
  }
  return count
})

const typeOptions = [
  { value: 'true_false', label: '判断题' },
  { value: 'single_choice', label: '单选题' },
  { value: 'multiple_choice', label: '多选题' },
  { value: 'fill_blank', label: '填空题' },
  { value: 'short_answer', label: '简答题' },
]

function getEffectiveType(q: any) {
  return q._userType || q.question?.question_type || q.llm_question_type || 'short_answer'
}
function getEffectiveAnswer(q: any) {
  return q._userAnswer ?? q.question?.correct_answer ?? ''
}
function getFullStem(q: any) { return q.question?.stem || '' }
function getOptions(q: any) {
  const opts = q.question?.options
  return opts && typeof opts === 'object' && Object.keys(opts).length > 0 ? opts : null
}
function getOptionsOrDefault(q: any) {
  const opts = getOptions(q)
  if (opts) return opts
  const t = getEffectiveType(q)
  if (t === 'true_false') return { T: '正确', F: '错误' }
  return {}
}
function hasOptions(q: any) {
  const t = getEffectiveType(q)
  return ['single_choice', 'multiple_choice', 'true_false'].includes(t)
}
function getOptionKeys(q: any) {
  const opts = getOptionsOrDefault(q)
  return Object.keys(opts)
}
function getAnswerPlaceholder(q: any) {
  const t = getEffectiveType(q)
  if (t === 'fill_blank') return '填空答案'
  return '输入参考答案'
}
function getConfidenceColor(c: number) {
  if (c >= 0.8) return 'green'
  if (c >= 0.5) return 'orange'
  return 'red'
}
function getStatus(q: any) {
  const answer = getEffectiveAnswer(q)
  const t = getEffectiveType(q)
  const objectiveTypes = ['single_choice', 'multiple_choice', 'true_false']
  if (!answer && objectiveTypes.includes(t)) return 'error'
  if (q.issues && q.issues.length > 0) return 'warn'
  if (llmEnhanced.value) {
    if ((q.type_confidence || 0) < 0.8 || (q.answer_confidence || 0) < 0.8) return 'warn'
    if (q.llm_type_differs) return 'warn'
  }
  return 'ok'
}
function getCardClass(q: any) {
  const s = getStatus(q)
  if (s === 'error') return 'card-error'
  if (s === 'warn') return 'card-warn'
  return 'card-ok'
}

function onTypeChange(q: any, value: string) {
  q._userType = value
  if (q.question) q.question.question_type = value
}
function onAnswerChange(q: any, value: string) {
  q._userAnswer = value
  if (q.question) q.question.correct_answer = value
}
function onStemChange(q: any, value: string) {
  if (q.question) q.question.stem = value
}
function onOptionChange(q: any, key: string, value: string) {
  if (q.question && q.question.options) {
    q.question.options[key] = value
  }
}

function acceptLLMSuggestion(q: any) {
  if (q.llm_question_type) onTypeChange(q, q.llm_question_type)
  if (q.llm_correct_answer) onAnswerChange(q, q.llm_correct_answer)
  message.success(`Q${q.order_num} 已采纳 AI 建议`)
}

function acceptAllLLM() {
  let count = 0
  for (const sec of sections.value) {
    for (const q of sec.questions) {
      const conf = Math.min(q.type_confidence || 0, q.answer_confidence || 0)
      if (conf >= 0.7) {
        if (q.llm_question_type) onTypeChange(q, q.llm_question_type)
        if (q.llm_correct_answer) onAnswerChange(q, q.llm_correct_answer)
        count++
      }
    }
  }
  message.success(`已采纳 ${count} 题的 AI 建议`)
}

function jumpToNextIssue() {
  for (const sec of sections.value) {
    for (const q of sec.questions) {
      if (getStatus(q) !== 'ok') {
        const el = document.getElementById(`q-${q.order_num}`)
        el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
        return
      }
    }
  }
}

// Build final data for import
function buildFinalData() {
  const data = JSON.parse(JSON.stringify(parsedData.value))
  const paper = data.paper || data

  let secIdx = 0
  for (const sec of paper.sections || []) {
    const uiSec = sections.value[secIdx]
    if (uiSec) {
      sec.questions = uiSec.questions.map((q: any) => {
        const clone = { ...q }
        delete clone._userType
        delete clone._userAnswer
        return clone
      })
    }
    secIdx++
  }
  if (sections.value.length > (paper.sections || []).length) {
    const lastSec = sections.value[sections.value.length - 1]
    paper.unsectioned_questions = lastSec.questions.map((q: any) => {
      const clone = { ...q }
      delete clone._userType
      delete clone._userAnswer
      return clone
    })
  }
  return data
}

async function handleConfirmImport() {
  importing.value = true
  try {
    const data = buildFinalData()
    const result: any = await request.post('/papers/import-reviewed', data)
    message.success('试卷导入成功')
    emit('imported', result)
  } catch (e) {
    message.error('导入失败')
  } finally {
    importing.value = false
  }
}
</script>

<style scoped>
.question-card {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  transition: border-color 0.2s;
}
.card-ok {
  border-left: 3px solid #52c41a;
}
.card-warn {
  border-left: 3px solid #faad14;
  background: #fffbe6;
}
.card-error {
  border-left: 3px solid #ff4d4f;
  background: #fff2f0;
}
.q-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.q-num {
  font-weight: 600;
  font-size: 14px;
  min-width: 60px;
}
.q-field {
  margin-bottom: 10px;
}
.q-field label {
  display: block;
  font-size: 12px;
  color: #666;
  margin-bottom: 4px;
  font-weight: 500;
}
.options-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.option-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.option-key {
  font-weight: 600;
  min-width: 20px;
}
</style>
