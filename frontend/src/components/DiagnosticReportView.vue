<template>
  <div>
    <h2 style="text-align: center; margin-bottom: 20px; font-size: 22px">
      {{ userName }} AI素养评测诊断分析报告
    </h2>

    <a-row :gutter="16" style="margin-bottom: 16px">
      <a-col :span="6">
        <a-card :bordered="false">
          <a-statistic title="总分" :value="diagnostic.total_score" :suffix="`/ ${diagnostic.max_score}`" />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card :bordered="false">
          <a-statistic title="得分率" :value="(diagnostic.ratio * 100).toFixed(0)" suffix="%" />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card :bordered="false">
          <a-statistic title="等级">
            <template #formatter>
              <a-tag :color="levelColor(diagnostic.level)" style="font-size: 20px; padding: 4px 16px">
                {{ diagnostic.level }}
              </a-tag>
            </template>
          </a-statistic>
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card :bordered="false">
          <a-statistic title="百分位排名" :value="diagnostic.percentile_rank != null ? `前${(100 - diagnostic.percentile_rank).toFixed(0)}%` : '-'" />
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

    <a-card title="错题分析" :bordered="false" style="margin-bottom: 16px">
      <a-alert
        v-if="!(diagnostic.wrong_answer_summary?.items || []).length"
        type="success"
        message="本次测评没有失分题。"
        show-icon
      />
      <template v-else>
        <a-alert
          type="info"
          :message="diagnostic.wrong_answer_summary?.overview || '已根据失分题汇总主要问题。'"
          show-icon
          style="margin-bottom: 12px"
        />
        <div
          v-for="item in (diagnostic.wrong_answer_summary?.items || [])"
          :key="item.question_id"
          style="padding: 16px; border: 1px solid #f0f0f0; border-radius: 8px; margin-bottom: 12px;"
        >
          <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px;">
            <a-tag color="orange">{{ item.dimension || '未分类' }}</a-tag>
            <a-tag>{{ typeLabel(item.question_type) }}</a-tag>
            <a-tag color="red">{{ item.earned_score }}/{{ item.max_score }}分</a-tag>
          </div>
          <div style="font-weight: 600; margin-bottom: 8px;">{{ item.stem }}</div>
          <div style="margin-bottom: 6px;"><strong>你的答案：</strong>{{ item.user_answer || '(未作答)' }}</div>
          <div style="margin-bottom: 6px;"><strong>参考答案：</strong>{{ item.reference_answer || item.correct_answer || '-' }}</div>
          <div style="margin-bottom: 6px;" v-if="item.reason_summary"><strong>错误原因：</strong>{{ item.reason_summary }}</div>
          <div style="margin-bottom: 6px;" v-if="item.improvement_tip"><strong>改进提示：</strong>{{ item.improvement_tip }}</div>
          <div v-if="item.missed_points?.length" style="margin-bottom: 6px;">
            <strong>遗漏要点：</strong>{{ item.missed_points.join('；') }}
          </div>
          <div style="color: #666;" v-if="item.explanation"><strong>题目解析：</strong>{{ item.explanation }}</div>
        </div>
        <a-alert
          v-if="diagnostic.wrong_answer_summary?.patterns?.length"
          type="warning"
          show-icon
        >
          <template #message>
            高频问题：{{ diagnostic.wrong_answer_summary.patterns.join('；') }}
          </template>
        </a-alert>
      </template>
    </a-card>

    <a-card title="维度分析" :bordered="false" style="margin-bottom: 16px">
      <a-row :gutter="16">
        <a-col :span="8" v-for="item in dimensionAnalysisList" :key="item.dimension">
          <a-card size="small" :bordered="true" style="margin-bottom: 12px">
            <template #title>
              <a-tag :color="levelColor(item.level)">{{ item.level }}</a-tag>
              {{ item.dimension }}
            </template>
            <div v-if="item.evaluated" style="margin-bottom: 8px">
              <a-progress :percent="item.score" :stroke-color="getProgressColor(item.score)" size="small" />
            </div>
            <div v-else style="margin-bottom: 8px; color: #999; font-size: 12px;">
              本次无题目覆盖
            </div>
            <p style="color: #666; font-size: 13px; margin: 0 0 8px 0">{{ item.description }}</p>
            <p style="font-size: 13px; margin: 0 0 8px 0">{{ item.summary || item.detail }}</p>
            <p v-if="item.evidence?.length" style="color: #999; font-size: 12px; margin: 0;">
              依据：{{ item.evidence.join('；') }}
            </p>
          </a-card>
        </a-col>
      </a-row>
    </a-card>

    <a-card title="个性化总结" :bordered="false" style="margin-bottom: 16px">
      <p style="margin-bottom: 12px; line-height: 1.8;">
        {{ diagnostic.personalized_summary?.summary || '暂无个性化总结。' }}
      </p>
      <a-row :gutter="16">
        <a-col :span="12">
          <a-card size="small" title="表现亮点">
            <a-list :data-source="diagnostic.personalized_summary?.highlights || []" size="small">
              <template #renderItem="{ item }">
                <a-list-item>{{ item }}</a-list-item>
              </template>
            </a-list>
          </a-card>
        </a-col>
        <a-col :span="12">
          <a-card size="small" title="关注点">
            <a-list :data-source="diagnostic.personalized_summary?.cautions || []" size="small">
              <template #renderItem="{ item }">
                <a-list-item>{{ item }}</a-list-item>
              </template>
            </a-list>
          </a-card>
        </a-col>
      </a-row>
    </a-card>

    <a-row :gutter="16" style="margin-bottom: 16px">
      <a-col :span="12">
        <a-card title="优势维度" :bordered="false">
          <a-list :data-source="diagnostic.strengths || []" size="small">
            <template #renderItem="{ item }">
              <a-list-item>
                <a-tag color="green">{{ item.dimension }}</a-tag>
                <span>{{ item.comment }} ({{ item.score }}分)</span>
              </a-list-item>
            </template>
            <template #header v-if="!(diagnostic.strengths || []).length">
              <span style="color: #999">暂无数据</span>
            </template>
          </a-list>
        </a-card>
      </a-col>
      <a-col :span="12">
        <a-card title="提升方向" :bordered="false">
          <a-list :data-source="diagnostic.improvement_priorities || []" size="small">
            <template #renderItem="{ item }">
              <a-list-item>
                <div style="width: 100%;">
                  <div style="margin-bottom: 4px;">
                    <a-tag color="orange">{{ item.dimension }}</a-tag>
                    <strong>{{ item.reason }}</strong>
                  </div>
                  <div v-if="item.actions?.length" style="color: #666;">
                    建议动作：{{ item.actions.join('；') }}
                  </div>
                </div>
              </a-list-item>
            </template>
            <template #header v-if="!(diagnostic.improvement_priorities || []).length">
              <span style="color: #999">暂无数据</span>
            </template>
          </a-list>
        </a-card>
      </a-col>
    </a-row>

    <a-card title="个性化学习建议" :bordered="false">
      <a-list :data-source="diagnostic.actionable_suggestions || []" size="small">
        <template #renderItem="{ item }">
          <a-list-item>
            <div style="width: 100%;">
              <div style="margin-bottom: 4px;">
                <a-tag color="blue">{{ item.dimension }}</a-tag>
                <strong>{{ item.title }}</strong>
              </div>
              <div>{{ item.suggestion }}</div>
              <div v-if="item.actions?.length" style="color: #666; margin-top: 4px;">
                可执行动作：{{ item.actions.join('；') }}
              </div>
            </div>
          </a-list-item>
        </template>
        <template #header v-if="!(diagnostic.actionable_suggestions || []).length">
          <span style="color: #999">暂无建议</span>
        </template>
      </a-list>
    </a-card>

    <a-card title="推荐资源" :bordered="false" style="margin-top: 16px">
      <a-list :data-source="diagnostic.recommended_resources || []" size="small">
        <template #renderItem="{ item }">
          <a-list-item>
            <div style="width: 100%;">
              <div style="margin-bottom: 4px;">
                <a-tag color="purple">{{ item.dimension }}</a-tag>
                <strong>{{ item.title }}</strong>
                <span style="color: #999; margin-left: 8px;">难度 {{ item.difficulty }}</span>
              </div>
              <div style="color: #666;">{{ item.match_reason }}</div>
            </div>
          </a-list-item>
        </template>
        <template #header v-if="!(diagnostic.recommended_resources || []).length">
          <span style="color: #999">暂无匹配课程资源</span>
        </template>
      </a-list>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
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
}>()

echarts.use([
  RadarChart, BarChart, TitleComponent, TooltipComponent,
  LegendComponent, RadarComponent, GridComponent, CanvasRenderer,
])

const radarChartRef = ref<HTMLElement | null>(null)
const barChartRef = ref<HTMLElement | null>(null)
const dimensionAnalysisList = computed(() => {
  const analysis = props.diagnostic?.dimension_analysis || {}
  return Object.entries(analysis).map(([dimension, item]: [string, any]) => ({
    dimension,
    ...item,
  }))
})

let radarChart: echarts.ECharts | null = null
let barChart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

function typeLabel(t: string) {
  return { single_choice: '单选题', multiple_choice: '多选题', true_false: '判断题', fill_blank: '填空题', short_answer: '简答题' }[t] || t
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

function renderRadarChart() {
  if (!radarChartRef.value || !props.diagnostic?.radar_data) return

  if (radarChart) radarChart.dispose()
  radarChart = echarts.init(radarChartRef.value)

  const radarData = props.diagnostic.radar_data
  const indicators = radarData.map((item: any) => ({
    name: item.evaluated ? item.dimension : `${item.dimension}（未评估）`,
    max: 100,
  }))
  const values = radarData.map((item: any) => item.evaluated ? item.score : null)

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
  if (!barChartRef.value || !props.diagnostic?.comparison) return

  if (barChart) barChart.dispose()
  barChart = echarts.init(barChartRef.value)

  const items = props.diagnostic.comparison.items || []
  const dims = items.map((i: any) => i.evaluated ? i.dimension : `${i.dimension}（未评估）`)
  const userScores = items.map((i: any) => i.user_score)
  const avgScores = items.map((i: any) => i.avg_score)

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
    if (radarReady && barReady) {
      return
    }
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
