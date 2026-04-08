<template>
  <div class="page-container">
    <div class="page-header">
      <h2>试卷归档</h2>
      <a-button @click="router.push('/papers')">
        <template #icon><ArrowLeftOutlined /></template>
        返回试卷管理
      </a-button>
    </div>

    <a-card class="filter-card" :bordered="false">
      <a-row :gutter="16">
        <a-col :span="8">
          <a-input v-model:value="keyword" placeholder="搜索试卷标题" allow-clear @press-enter="fetchArchived">
            <template #prefix><SearchOutlined /></template>
          </a-input>
        </a-col>
        <a-col :span="4">
          <a-button type="primary" @click="fetchArchived">查询</a-button>
          <a-button style="margin-left: 8px" @click="keyword = ''; fetchArchived()">重置</a-button>
        </a-col>
      </a-row>
    </a-card>

    <a-card class="card-container" :bordered="false">
      <a-alert
        message="归档说明"
        description="归档试卷不会出现在试卷管理列表中。您可以「恢复」试卷为草稿状态继续编辑，或「彻底删除」永久移除。"
        type="info"
        show-icon
        closable
        style="margin-bottom: 16px"
      />

      <a-table
        :columns="columns"
        :data-source="papers"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'total_score'">
            {{ record.total_score }} 分
          </template>
          <template v-if="column.key === 'question_count'">
            {{ record.question_count ?? 0 }} 题
          </template>
          <template v-if="column.key === 'created_at'">
            {{ formatDate(record.created_at) }}
          </template>
          <template v-if="column.key === 'updated_at'">
            {{ formatDate(record.updated_at) }}
          </template>
          <template v-if="column.key === 'actions'">
            <a-space>
              <a-popconfirm title="确定恢复此试卷？恢复后将变为草稿状态。" @confirm="restorePaper(record)">
                <a style="color: #52c41a"><UndoOutlined /> 恢复</a>
              </a-popconfirm>
              <a-popconfirm title="确定彻底删除此试卷？此操作不可撤销！" ok-text="确定删除" ok-type="danger" @confirm="permanentDelete(record)">
                <a style="color: #ff4d4f"><DeleteOutlined /> 彻底删除</a>
              </a-popconfirm>
            </a-space>
          </template>
        </template>

        <template #emptyText>
          <a-empty description="暂无归档试卷" />
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, SearchOutlined, UndoOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import request from '@/utils/request'

const router = useRouter()

const loading = ref(false)
const papers = ref<any[]>([])
const keyword = ref('')
const pagination = reactive({ current: 1, pageSize: 20, total: 0 })

const columns = [
  { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
  { title: '总分', key: 'total_score', width: 80 },
  { title: '题目数', key: 'question_count', width: 80 },
  { title: '创建时间', key: 'created_at', width: 160 },
  { title: '归档时间', key: 'updated_at', width: 160 },
  { title: '操作', key: 'actions', width: 200 },
]

function formatDate(d: string) {
  if (!d) return ''
  return new Date(d).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function fetchArchived() {
  loading.value = true
  try {
    const params: any = {
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize,
      status: 'archived',
    }
    if (keyword.value) params.keyword = keyword.value
    const data: any = await request.get('/papers', { params })
    papers.value = data.data || []
    pagination.total = data.total || 0
  } catch { /* handled */ } finally {
    loading.value = false
  }
}

function handleTableChange(pag: any) {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  fetchArchived()
}

async function restorePaper(record: any) {
  try {
    await request.post(`/papers/${record.id}/restore`)
    message.success('已恢复为草稿')
    fetchArchived()
  } catch { /* handled */ }
}

async function permanentDelete(record: any) {
  try {
    await request.delete(`/papers/${record.id}`)
    message.success('已彻底删除')
    fetchArchived()
  } catch { /* handled */ }
}

onMounted(() => { fetchArchived() })
</script>

<style scoped>
.filter-card { margin-bottom: 16px; }
</style>
