<template>
  <div class="page-container">
    <div class="page-header">
      <h2>工作面板</h2>
    </div>

    <!-- LLM Status Warning -->
    <a-alert
      v-if="llmWarning"
      :message="llmWarning.title"
      :description="llmWarning.desc"
      type="warning"
      show-icon
      closable
      style="margin-bottom: 16px"
    >
      <template #action>
        <a-button size="small" type="primary" ghost @click="$router.push('/system-config')">
          前往配置
        </a-button>
      </template>
    </a-alert>

    <!-- Stats Cards -->
    <a-row :gutter="[16, 16]">
      <a-col :xs="12" :lg="6">
        <a-card class="stat-card">
          <a-statistic title="素材总数" :value="stats.materials" :value-style="{ color: '#1F4E79' }">
            <template #prefix><FolderOutlined /></template>
          </a-statistic>
        </a-card>
      </a-col>
      <a-col :xs="12" :lg="6">
        <a-card class="stat-card">
          <a-statistic title="题目总数" :value="stats.questions" :value-style="{ color: '#2A6BA6' }">
            <template #prefix><FileTextOutlined /></template>
          </a-statistic>
        </a-card>
      </a-col>
      <a-col :xs="12" :lg="6">
        <a-card class="stat-card">
          <a-statistic title="考试数量" :value="stats.exams" :value-style="{ color: '#3D8ED0' }">
            <template #prefix><FormOutlined /></template>
          </a-statistic>
        </a-card>
      </a-col>
      <a-col :xs="12" :lg="6">
        <a-card class="stat-card">
          <a-statistic title="用户总数" :value="stats.users" :value-style="{ color: '#52c41a' }">
            <template #prefix><TeamOutlined /></template>
          </a-statistic>
        </a-card>
      </a-col>
    </a-row>

    <a-row :gutter="[24, 24]" style="margin-top: 24px;">
      <a-col :xs="24" :lg="12">
        <a-card title="AI素养维度题目占比" class="card-container">
          <div class="dimension-list">
            <div v-for="dim in dimensions" :key="dim.name" class="dimension-item">
              <span class="dim-name">{{ dim.name }}</span>
              <a-progress :percent="dim.coverage" :stroke-color="primaryColor" size="small" />
            </div>
          </div>
        </a-card>
      </a-col>

      <a-col :xs="24" :lg="12">
        <a-card title="近期考试" class="card-container">
          <a-list size="small" :data-source="recentExams" :locale="{ emptyText: '暂无考试数据' }">
            <template #renderItem="{ item }">
              <a-list-item>
                <a-list-item-meta :title="item.title">
                  <template #description>
                    <a-space>
                      <a-tag :color="item.status === 'published' ? 'green' : 'default'">
                        {{ item.status === 'published' ? '进行中' : item.status === 'draft' ? '草稿' : '已关闭' }}
                      </a-tag>
                      <span>总分 {{ item.total_score }}</span>
                      <span>{{ item.usage_count || 0 }} 人参加</span>
                    </a-space>
                  </template>
                </a-list-item-meta>
              </a-list-item>
            </template>
          </a-list>
        </a-card>
      </a-col>
    </a-row>

    <a-row :gutter="[24, 24]" style="margin-top: 24px;">
      <a-col :xs="24" :lg="12">
        <a-card title="待审核题目" class="card-container">
          <a-list size="small" :data-source="pendingQuestions" :locale="{ emptyText: '暂无待审核题目' }">
            <template #renderItem="{ item }">
              <a-list-item>
                <a-list-item-meta>
                  <template #title>{{ item.stem?.substring(0, 60) }}{{ (item.stem?.length || 0) > 60 ? '...' : '' }}</template>
                  <template #description>
                    <a-space>
                      <a-tag>{{ typeLabel(item.question_type) }}</a-tag>
                      <span>难度 {{ item.difficulty }}</span>
                    </a-space>
                  </template>
                </a-list-item-meta>
              </a-list-item>
            </template>
          </a-list>
        </a-card>
      </a-col>

      <a-col :xs="24" :lg="12">
        <a-card title="最新素材" class="card-container">
          <a-list size="small" :data-source="recentMaterials" :locale="{ emptyText: '暂无素材' }">
            <template #renderItem="{ item }">
              <a-list-item>
                <a-list-item-meta :title="item.title">
                  <template #description>
                    <a-space>
                      <a-tag>{{ item.format }}</a-tag>
                      <span>{{ item.category || '未分类' }}</span>
                    </a-space>
                  </template>
                </a-list-item-meta>
              </a-list-item>
            </template>
          </a-list>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { FolderOutlined, FileTextOutlined, FormOutlined, TeamOutlined } from '@ant-design/icons-vue'
import request from '@/utils/request'

const primaryColor = '#1F4E79'

const llmWarning = ref<{ title: string; desc: string } | null>(null)
const stats = ref({ materials: 0, questions: 0, exams: 0, users: 0 })
const recentExams = ref<any[]>([])
const pendingQuestions = ref<any[]>([])
const recentMaterials = ref<any[]>([])

const dimensions = ref([
  { name: 'AI基础知识', coverage: 0 },
  { name: 'AI技术应用', coverage: 0 },
  { name: 'AI伦理安全', coverage: 0 },
  { name: 'AI批判思维', coverage: 0 },
  { name: 'AI创新实践', coverage: 0 },
  { name: '未分类', coverage: 0 },
])

function typeLabel(t: string) {
  return { single_choice: '单选题', multiple_choice: '多选题', true_false: '判断题', fill_blank: '填空题', short_answer: '简答题' }[t] || t
}

async function loadDashboard() {
  const results = await Promise.allSettled([
    request.get('/materials', { params: { skip: 0, limit: 5 } }),
    request.get('/questions', { params: { skip: 0, limit: 5, status: 'pending_review' } }),
    request.get('/questions/stats', { params: { status: 'approved' } }),
    request.get('/exams', { params: { skip: 0, limit: 5, is_random_test: false } }),
    request.get('/users/stats'),
  ])

  if (results[0].status === 'fulfilled') {
    const d = results[0].value as any
    stats.value.materials = d.total || 0
    recentMaterials.value = d.items?.slice(0, 5) || []
  }
  if (results[1].status === 'fulfilled') {
    const d = results[1].value as any
    pendingQuestions.value = d.items?.slice(0, 5) || []
  }
  if (results[2].status === 'fulfilled') {
    const d = results[2].value as any
    stats.value.questions = d.total || 0
    const byDimension = d.by_dimension || {}
    const totalQuestions = d.total || 0
    dimensions.value.forEach(dimensionItem => {
      const count = byDimension[dimensionItem.name] || 0
      dimensionItem.coverage = totalQuestions > 0
        ? Math.round((count / totalQuestions) * 100)
        : 0
    })
  }
  if (results[3].status === 'fulfilled') {
    const d = results[3].value as any
    stats.value.exams = d.total || 0
    recentExams.value = d.items?.slice(0, 5) || []
  }
  if (results[4].status === 'fulfilled') {
    const d = results[4].value as any
    stats.value.users = d.total || 0
  }
}

async function checkLLMStatus() {
  try {
    const data: any = await request.get('/system/llm-status')
    if (!data.configured) {
      llmWarning.value = {
        title: 'AI 大模型尚未配置',
        desc: '题目生成、智能评分、试卷解析等功能需要配置大模型才能正常工作，当前将使用规则降级模式（功能受限）。',
      }
    } else if (data.unconfigured_modules?.length > 0) {
      const names = data.unconfigured_modules.map((m: any) => m.name).join('、')
      llmWarning.value = {
        title: '部分 AI 功能未配置大模型',
        desc: `以下功能将使用规则降级模式：${names}。建议在系统配置中为所有模块分配模型提供者。`,
      }
    }
  } catch { /* non-admin users may not have access, ignore */ }
}

onMounted(() => { loadDashboard(); checkLLMStatus() })
</script>

<style scoped>
.stat-card { text-align: center; }
.dimension-list { display: flex; flex-direction: column; gap: 16px; }
.dimension-item { display: flex; align-items: center; gap: 12px; }
.dim-name { white-space: nowrap; width: 120px; font-size: 14px; }
</style>
