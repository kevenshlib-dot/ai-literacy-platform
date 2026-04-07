<template>
  <div class="page-container">
    <div class="page-header">
      <h2>工作台</h2>
    </div>

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
        <a-card class="card-container">
          <template #title>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>待审核题目</span>
              <a-button type="link" size="small" style="color: #1F4E79; font-weight: 500;" @click="goToBatchReview">
                <template #icon><AuditOutlined /></template>
                批量审核
              </a-button>
            </div>
          </template>
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
          <div v-if="materialBatches.length === 0" style="text-align: center; color: #999; padding: 24px 0;">
            暂无素材
          </div>
          <div v-for="(batch, bIdx) in materialBatches" :key="bIdx" class="material-batch">
            <div class="batch-header">
              <span class="batch-time">{{ batch.label }}</span>
              <a-tag color="blue" size="small">{{ batch.items.length }} 份</a-tag>
            </div>
            <a-list size="small" :data-source="batch.items" :split="false">
              <template #renderItem="{ item }">
                <a-list-item style="padding: 4px 0 4px 12px;">
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
          </div>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { FolderOutlined, FileTextOutlined, FormOutlined, TeamOutlined, AuditOutlined } from '@ant-design/icons-vue'
import request from '@/utils/request'

const router = useRouter()
const primaryColor = '#1F4E79'

const stats = ref({ materials: 0, questions: 0, exams: 0, users: 0 })
const recentExams = ref<any[]>([])
const pendingQuestions = ref<any[]>([])

interface MaterialBatch {
  label: string
  items: any[]
}
const materialBatches = ref<MaterialBatch[]>([])

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

function goToBatchReview() {
  router.push('/questions?tab=review')
}

/**
 * Group materials into upload batches.
 * Materials uploaded within 120 seconds by the same user are considered the same batch.
 * Returns the most recent 3 batches, with items sorted by title pinyin within each batch.
 */
function groupIntoBatches(materials: any[]): MaterialBatch[] {
  if (!materials || materials.length === 0) return []

  // Materials are already sorted by created_at DESC from the API
  const batches: { time: Date; uploadedBy: string; items: any[] }[] = []

  for (const m of materials) {
    const mTime = new Date(m.created_at)
    const uploader = m.uploaded_by || ''

    if (batches.length === 0) {
      batches.push({ time: mTime, uploadedBy: uploader, items: [m] })
      continue
    }

    const lastBatch = batches[batches.length - 1]!
    const timeDiff = Math.abs(lastBatch.time.getTime() - mTime.getTime()) / 1000

    if (timeDiff <= 120 && lastBatch.uploadedBy === uploader) {
      lastBatch.items.push(m)
    } else {
      if (batches.length >= 3) break
      batches.push({ time: mTime, uploadedBy: uploader, items: [m] })
    }
  }

  // Sort within each batch by title pinyin, then format the label
  return batches.slice(0, 3).map(b => {
    b.items.sort((a: any, b: any) => (a.title || '').localeCompare(b.title || '', 'zh-Hans'))
    const d = b.time
    const label = `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')} 上传`
    return { label, items: b.items }
  })
}

async function loadDashboard() {
  const results = await Promise.allSettled([
    request.get('/materials', { params: { skip: 0, limit: 100 } }),
    request.get('/questions', { params: { skip: 0, limit: 5, status: 'pending_review' } }),
    request.get('/questions/stats', { params: { status: 'approved' } }),
    request.get('/exams', { params: { skip: 0, limit: 5, is_random_test: false } }),
    request.get('/users/stats'),
  ])

  if (results[0].status === 'fulfilled') {
    const d = results[0].value as any
    stats.value.materials = d.total || 0
    const allMaterials = d.data || d.items || []
    materialBatches.value = groupIntoBatches(allMaterials)
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

onMounted(() => { loadDashboard() })
</script>

<style scoped>
.stat-card { text-align: center; }
.dimension-list { display: flex; flex-direction: column; gap: 16px; }
.dimension-item { display: flex; align-items: center; gap: 12px; }
.dim-name { white-space: nowrap; width: 120px; font-size: 14px; }

.material-batch {
  margin-bottom: 12px;
}
.material-batch:last-child {
  margin-bottom: 0;
}
.batch-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid #f0f0f0;
  margin-bottom: 4px;
}
.batch-time {
  font-size: 13px;
  color: #666;
  font-weight: 500;
}
</style>
