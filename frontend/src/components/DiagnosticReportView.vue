<template>
  <div>
    <h2 style="text-align: center; margin-bottom: 20px; font-size: 22px">
      {{ userName }} AI素养评测诊断分析报告
    </h2>

    <a-row :gutter="16" style="margin-bottom: 16px">
      <a-col :span="6">
        <a-card :bordered="false">
          <a-statistic title="总分" :value="normalizedDiagnostic.total_score" :suffix="`/ ${normalizedDiagnostic.max_score}`" />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card :bordered="false">
          <a-statistic title="得分率" :value="(normalizedDiagnostic.ratio * 100).toFixed(0)" suffix="%" />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card :bordered="false">
          <a-statistic title="等级">
            <template #formatter>
              <a-tag :color="levelColor(normalizedDiagnostic.level)" style="font-size: 20px; padding: 4px 16px">
                {{ normalizedDiagnostic.level }}
              </a-tag>
            </template>
          </a-statistic>
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card :bordered="false">
          <a-statistic :value="percentileDisplay" title="百分位排名" />
        </a-card>
      </a-col>
    </a-row>

    <a-row :gutter="16" style="margin-bottom: 16px">
      <a-col :span="12">
        <a-card title="五维素养雷达图" :bordered="false">
          <div ref="radarChartRef" style="width: 100%; height: 360px"></div>
        </a-card>
      </a-col>
      <a-col :span="12">
        <a-card title="维度对比（个人 vs 平均）" :bordered="false">
          <div ref="barChartRef" style="width: 100%; height: 360px"></div>
        </a-card>
      </a-col>
    </a-row>

    <a-card title="维度分析" :bordered="false" style="margin-bottom: 16px">
      <a-row :gutter="16">
        <a-col v-for="(item, index) in normalizedDiagnostic.radar_data" :key="index" :span="8">
          <a-card size="small" :bordered="true" style="margin-bottom: 12px">
            <template #title>
              <a-tag :color="levelColor(item.level)">{{ item.level }}</a-tag>
              {{ item.dimension }}
            </template>
            <div v-if="item.evaluated !== false" style="margin-bottom: 8px">
              <a-progress :percent="item.score" :stroke-color="getProgressColor(item.score)" size="small" />
            </div>
            <div v-else style="margin-bottom: 8px; color: #999; font-size: 12px">
              本次无题目覆盖
            </div>
            <p style="color: #666; font-size: 13px; margin: 0">{{ item.description }}</p>
          </a-card>
        </a-col>
      </a-row>
      <a-alert
        v-if="normalizedDiagnostic.uncategorized_metrics?.evaluated"
        type="info"
        show-icon
        style="margin-top: 4px"
      >
        <template #message>
          未分类题目：{{ normalizedDiagnostic.uncategorized_metrics.earned }} /
          {{ normalizedDiagnostic.uncategorized_metrics.max }} 分，
          共 {{ normalizedDiagnostic.uncategorized_metrics.question_count }} 题，
          扣分 {{ normalizedDiagnostic.uncategorized_metrics.wrong_count }} 题。该部分不参与五维雷达统计。
        </template>
      </a-alert>
    </a-card>

    <a-row :gutter="16" style="margin-bottom: 16px">
      <a-col :span="12">
        <a-card title="优势维度" :bordered="false">
          <a-list :data-source="normalizedDiagnostic.strengths || []" size="small">
            <template #renderItem="{ item }">
              <a-list-item>
                <a-tag color="green">{{ item.dimension }}</a-tag>
                <span>{{ item.comment }} ({{ item.score }}分)</span>
              </a-list-item>
            </template>
            <template #header v-if="!(normalizedDiagnostic.strengths || []).length">
              <span style="color: #999">暂无数据</span>
            </template>
          </a-list>
        </a-card>
      </a-col>
      <a-col :span="12">
        <a-card title="提升方向" :bordered="false">
          <a-list :data-source="normalizedDiagnostic.weaknesses || []" size="small">
            <template #renderItem="{ item }">
              <a-list-item>
                <a-tag color="orange">{{ item.dimension }}</a-tag>
                <span>{{ item.comment }} ({{ item.score }}分)</span>
              </a-list-item>
            </template>
            <template #header v-if="!(normalizedDiagnostic.weaknesses || []).length">
              <span style="color: #999">暂无数据</span>
            </template>
          </a-list>
        </a-card>
      </a-col>
    </a-row>

    <a-card title="个性化学习建议" :bordered="false">
      <a-list :data-source="normalizedDiagnostic.recommendations || []" size="small">
        <template #renderItem="{ item }">
          <a-list-item>
            <a-tag :color="item.priority === '高' ? 'red' : item.priority === '中' ? 'orange' : 'blue'">
              {{ item.priority }}优先
            </a-tag>
            <strong>{{ item.dimension }}</strong>：{{ item.suggestion }}
          </a-list-item>
        </template>
      </a-list>
    </a-card>

    <a-card :bordered="false" style="margin-top: 16px">
      <template #title>
        <div style="display: flex; align-items: center; gap: 12px">
          <span style="font-size: 16px; font-weight: 600">批卷详情</span>
          <template v-if="fullReviewData">
            <a-tag color="green"><CheckCircleOutlined /> 满分 {{ fullReviewData.full_score_count ?? derivedFullScoreCount }} 题</a-tag>
            <a-tag color="red"><CloseCircleOutlined /> 扣分 {{ fullReviewData.deducted_count ?? derivedDeductedCount }} 题</a-tag>
            <a-tag>共 {{ fullReviewData.total }} 题</a-tag>
          </template>
        </div>
      </template>
      <a-spin :spinning="fullReviewLoading">
        <a-empty v-if="!fullReviewData?.items?.length && !fullReviewLoading" description="暂无数据" />
        <div
          v-for="(item, idx) in (fullReviewData?.items || [])"
          :key="idx"
          :style="{
            marginBottom: '16px',
            padding: '16px',
            borderRadius: '8px',
            borderLeft: `5px solid ${scoreStatusBorderColor(item)}`,
            background: scoreStatusBackground(item),
          }"
        >
          <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap">
            <span style="font-weight: 700; font-size: 15px; color: #333">第 {{ item.order_num }} 题</span>
            <a-tag>{{ typeLabel(item.question_type) }}</a-tag>
            <a-tag :color="item.dimension ? 'blue' : 'default'">{{ item.dimension || '未分类' }}</a-tag>
            <a-tag :color="scoreStatusTagColor(item)" style="font-weight: 600">
              <CheckCircleOutlined v-if="scoreStatusIconName(item) === 'check'" />
              <CloseCircleOutlined v-else-if="scoreStatusIconName(item) === 'close'" />
              <ExclamationCircleOutlined v-else />
              {{ scoreStatusLabel(item) }}
            </a-tag>
            <a-tag :color="hasDeduction(item) ? 'red' : 'green'">
              {{ item.earned_score }} / {{ item.max_score }} 分
            </a-tag>
            <a-button size="small" type="link" style="margin-left: auto" @click="openComplaint(item)">
              <ExclamationCircleOutlined /> 反馈投诉
            </a-button>
          </div>

          <div style="font-size: 15px; line-height: 1.8; margin-bottom: 12px; color: #333">{{ item.stem }}</div>

          <div v-if="item.options" style="margin-bottom: 12px">
            <div
              v-for="(val, key) in item.options"
              :key="key"
              :style="{
                padding: '8px 12px',
                borderRadius: '6px',
                marginBottom: '6px',
                background: isCorrectOption(key as string, item.correct_answer) ? '#d9f7be'
                  : isUserWrongOption(key as string, item.user_answer, item.correct_answer) ? '#ffa39e40' : '#fafafa',
                border: isCorrectOption(key as string, item.correct_answer) ? '1px solid #95de64'
                  : isUserWrongOption(key as string, item.user_answer, item.correct_answer) ? '1px solid #ff7875' : '1px solid #f0f0f0',
                fontWeight: isCorrectOption(key as string, item.correct_answer) || isUserWrongOption(key as string, item.user_answer, item.correct_answer) ? '600' : 'normal',
              }"
            >
              {{ key }}. {{ val }}
              <a-tag v-if="isCorrectOption(key as string, item.correct_answer)" color="green" size="small" style="margin-left: 8px">正确答案</a-tag>
              <a-tag v-if="isUserCorrectOption(key as string, item.user_answer, item.correct_answer)" color="green" size="small" style="margin-left: 4px">✓ 你的选择</a-tag>
              <a-tag v-if="isUserWrongOption(key as string, item.user_answer, item.correct_answer)" color="red" size="small" style="margin-left: 4px">✗ 你的选择</a-tag>
            </div>
          </div>

          <div v-if="!item.options" style="margin-bottom: 12px; padding: 12px; background: #fafafa; border-radius: 6px">
            <div style="margin-bottom: 8px"><strong>你的答案：</strong><span :style="{ color: hasDeduction(item) ? '#ff4d4f' : '#333' }">{{ item.user_answer || '（未作答）' }}</span></div>
            <div v-if="item.correct_answer"><strong>参考答案：</strong><span style="color: #52c41a">{{ item.correct_answer }}</span></div>
          </div>

          <a-alert
            :type="scoreStatusAlertType(item)"
            show-icon
            style="margin-top: 8px"
          >
            <template #message>
              <div>
                <strong>评语：</strong>{{ item.feedback || '暂无评语' }}
              </div>
              <div v-if="item.explanation" style="margin-top: 6px; color: #666">
                <strong>解析：</strong>{{ item.explanation }}
              </div>
            </template>
          </a-alert>
        </div>
      </a-spin>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { CheckCircleOutlined, CloseCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons-vue'
import * as echarts from 'echarts/core'
import { RadarChart, BarChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  RadarComponent,
  GridComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

const props = defineProps<{
  diagnostic: any
  userName: string
  fullReviewData?: any
  fullReviewLoading?: boolean
  openComplaint?: (item: any) => void
}>()

echarts.use([
  RadarChart, BarChart, TitleComponent, TooltipComponent,
  LegendComponent, RadarComponent, GridComponent, CanvasRenderer,
])

const radarChartRef = ref<HTMLElement | null>(null)
const barChartRef = ref<HTMLElement | null>(null)
const normalizedDiagnostic = computed(() => normalizeDiagnosticReport(props.diagnostic || {}))
const fullReviewData = computed(() => props.fullReviewData || null)
const fullReviewLoading = computed(() => Boolean(props.fullReviewLoading))
const fullReviewItems = computed(() => asArray(fullReviewData.value?.items))
const derivedFullScoreCount = computed(() => fullReviewItems.value.filter((item: any) => scoreStatus(item) === 'full_score').length)
const derivedDeductedCount = computed(() => fullReviewItems.value.filter((item: any) => hasDeduction(item)).length)
const percentileDisplay = computed(() => (
  normalizedDiagnostic.value.percentile_rank != null
    ? `前${(100 - normalizedDiagnostic.value.percentile_rank).toFixed(0)}%`
    : '-'
))

let radarChart: echarts.ECharts | null = null
let barChart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

function asArray(value: any): any[] {
  return Array.isArray(value) ? value : []
}

function isFiniteNumber(value: any): boolean {
  return typeof value === 'number' && Number.isFinite(value)
}

function scoreToLevel(score: number): string {
  if (score >= 90) return '优秀'
  if (score >= 80) return '良好'
  if (score >= 60) return '合格'
  return '需提升'
}

function normalizeRadarData(report: any) {
  return asArray(report.radar_data).map((item: any) => {
    const score = isFiniteNumber(item.score) ? item.score : 0
    return {
      ...item,
      score,
      max: item.max ?? 100,
      level: item.level || scoreToLevel(score),
      description: item.description || '',
    }
  })
}

function normalizeComparison(report: any, radarData: any[]) {
  const comparison = report.comparison || {}
  const sourceItems = asArray(comparison.items)
  const items = sourceItems.length
    ? sourceItems
    : radarData.map((item: any) => ({
        dimension: item.dimension,
        user_score: item.score,
        avg_score: 0,
        diff: null,
      }))

  return {
    ...comparison,
    items,
  }
}

function normalizeRecommendations(report: any) {
  const recommendations = Array.isArray(report.recommendations)
    ? report.recommendations
    : asArray(report.actionable_suggestions)

  return recommendations.map((item: any, index: number) => {
    if (typeof item === 'string') {
      return {
        dimension: '综合',
        priority: '中',
        suggestion: item,
      }
    }
    return {
      dimension: item.dimension || '综合',
      priority: item.priority || '中',
      suggestion: item.suggestion || item.comment || item.title || `学习建议 ${index + 1}`,
    }
  }).filter((item: any) => item.suggestion)
}

function normalizeDiagnosticReport(report: any) {
  const radarData = normalizeRadarData(report)
  return {
    ...report,
    total_score: report.total_score ?? 0,
    max_score: report.max_score ?? 0,
    ratio: isFiniteNumber(report.ratio)
      ? report.ratio
      : (report.max_score > 0 ? Number((report.total_score / report.max_score).toFixed(2)) : 0),
    level: report.level || '-',
    radar_data: radarData,
    comparison: normalizeComparison(report, radarData),
    uncategorized_metrics: report.uncategorized_metrics || null,
    strengths: asArray(report.strengths),
    weaknesses: asArray(report.weaknesses),
    recommendations: normalizeRecommendations(report),
  }
}

function typeLabel(t: string): string {
  const map: Record<string, string> = {
    single_choice: '单选题',
    multiple_choice: '多选题',
    true_false: '判断题',
    fill_blank: '填空题',
    short_answer: '简答题',
  }
  return map[t] || t
}

function levelColor(level: string): string {
  const map: Record<string, string> = {
    优秀: 'green',
    良好: 'blue',
    合格: 'orange',
    不合格: 'red',
    需提升: 'red',
  }
  return map[level] || 'default'
}

function getProgressColor(score: number): string {
  if (score >= 90) return '#52c41a'
  if (score >= 80) return '#1890ff'
  if (score >= 60) return '#faad14'
  return '#f5222d'
}

function scoreStatus(item: any): string {
  if (item?.score_status) return item.score_status
  if (item?.is_correct === null || item?.is_correct === undefined) return 'manual_review'
  const earned = Number(item?.earned_score ?? 0)
  const max = Number(item?.max_score ?? 0)
  if (max > 0 && earned >= max) return 'full_score'
  if (earned <= 0) return 'zero_score'
  return 'partial_score'
}

function hasDeduction(item: any): boolean {
  if (typeof item?.has_deduction === 'boolean') return item.has_deduction
  return Number(item?.earned_score ?? 0) < Number(item?.max_score ?? 0)
}

function scoreStatusLabel(item: any): string {
  const status = scoreStatus(item)
  if (status === 'full_score') return '满分'
  if (status === 'partial_score') return '扣分'
  if (status === 'zero_score') return '未得分'
  return '待人工判定'
}

function scoreStatusTagColor(item: any): string {
  const status = scoreStatus(item)
  if (status === 'full_score') return 'success'
  if (status === 'partial_score') return 'warning'
  if (status === 'zero_score') return 'error'
  return 'default'
}

function scoreStatusAlertType(item: any): 'success' | 'warning' | 'error' {
  const status = scoreStatus(item)
  if (status === 'full_score') return 'success'
  if (status === 'partial_score') return 'warning'
  if (status === 'zero_score') return 'error'
  return 'warning'
}

function scoreStatusBorderColor(item: any): string {
  const status = scoreStatus(item)
  if (status === 'full_score') return '#52c41a'
  if (status === 'partial_score') return '#faad14'
  if (status === 'zero_score') return '#ff4d4f'
  return '#d9d9d9'
}

function scoreStatusBackground(item: any): string {
  const status = scoreStatus(item)
  if (status === 'full_score') return '#f6ffed'
  if (status === 'partial_score') return '#fffbe6'
  if (status === 'zero_score') return '#fff1f0'
  return '#fafafa'
}

function scoreStatusIconName(item: any): string {
  const status = scoreStatus(item)
  if (status === 'full_score') return 'check'
  if (status === 'partial_score' || status === 'manual_review') return 'warning'
  return 'close'
}

function isCorrectOption(key: string, correctAnswer?: string): boolean {
  return correctAnswer?.toUpperCase().includes(key.toUpperCase()) || false
}

function isUserCorrectOption(key: string, userAnswer?: string, correctAnswer?: string): boolean {
  if (!userAnswer) return false
  const isUserChoice = userAnswer.toUpperCase().includes(key.toUpperCase())
  const isCorrect = correctAnswer?.toUpperCase().includes(key.toUpperCase())
  return isUserChoice && !!isCorrect
}

function isUserWrongOption(key: string, userAnswer?: string, correctAnswer?: string): boolean {
  if (!userAnswer) return false
  const isUserChoice = userAnswer.toUpperCase().includes(key.toUpperCase())
  const isCorrect = correctAnswer?.toUpperCase().includes(key.toUpperCase())
  return isUserChoice && !isCorrect
}

function openComplaint(item: any) {
  props.openComplaint?.(item)
}

function renderRadarChart() {
  if (!radarChartRef.value || !normalizedDiagnostic.value.radar_data?.length) return

  if (radarChart) radarChart.dispose()
  radarChart = echarts.init(radarChartRef.value)

  const radarData = normalizedDiagnostic.value.radar_data
  const indicators = radarData.map((item: any) => ({
    name: item.dimension,
    max: 100,
  }))
  const values = radarData.map((item: any) => item.score)

  radarChart.setOption({
    tooltip: {},
    radar: {
      indicator: indicators,
      shape: 'polygon',
      splitNumber: 5,
      axisName: { color: '#333', fontSize: 12 },
    },
    series: [{
      type: 'radar',
      data: [{
        value: values,
        name: '个人得分',
        areaStyle: { opacity: 0.3 },
        lineStyle: { width: 2 },
      }],
      symbol: 'circle',
      symbolSize: 6,
    }],
  })
}

function renderBarChart() {
  if (!barChartRef.value || !normalizedDiagnostic.value.comparison) return

  if (barChart) barChart.dispose()
  barChart = echarts.init(barChartRef.value)

  const items = normalizedDiagnostic.value.comparison.items || []
  const dims = items.map((item: any) => item.dimension)
  const userScores = items.map((item: any) => item.user_score)
  const avgScores = items.map((item: any) => item.avg_score)

  barChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['个人', '平均'] },
    grid: { left: 20, right: 20, bottom: 20, top: 40, containLabel: true },
    xAxis: {
      type: 'category',
      data: dims,
      axisLabel: { interval: 0, fontSize: 11 },
    },
    yAxis: { type: 'value', max: 100 },
    series: [
      {
        name: '个人',
        type: 'bar',
        data: userScores,
        itemStyle: { color: '#1F4E79' },
        barWidth: '30%',
      },
      {
        name: '平均',
        type: 'bar',
        data: avgScores,
        itemStyle: { color: '#bbb' },
        barWidth: '30%',
      },
    ],
  })
}

function resizeCharts() {
  radarChart?.resize()
  barChart?.resize()
}

function waitForAnimationFrame() {
  return new Promise<void>((resolve) => {
    requestAnimationFrame(() => resolve())
  })
}

async function waitForChartContainers() {
  for (let index = 0; index < 6; index += 1) {
    await nextTick()
    await waitForAnimationFrame()

    const radarReady = !!radarChartRef.value && radarChartRef.value.clientWidth > 0
    const barReady = !!barChartRef.value && barChartRef.value.clientWidth > 0
    if (radarReady && barReady) return
  }
}

async function renderCharts() {
  await waitForChartContainers()
  renderRadarChart()
  renderBarChart()
  await waitForAnimationFrame()
  resizeCharts()
}

watch(
  () => props.diagnostic,
  async (val) => {
    if (!val) return
    await renderCharts()
  },
  { deep: true }
)

onMounted(async () => {
  if (props.diagnostic) {
    await renderCharts()
  }

  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      resizeCharts()
    })
    if (radarChartRef.value) resizeObserver.observe(radarChartRef.value)
    if (barChartRef.value) resizeObserver.observe(barChartRef.value)
  }

  window.addEventListener('resize', resizeCharts)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  window.removeEventListener('resize', resizeCharts)
  if (radarChart) radarChart.dispose()
  if (barChart) barChart.dispose()
})
</script>
