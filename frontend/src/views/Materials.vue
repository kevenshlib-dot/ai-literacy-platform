<template>
  <div class="page-container">
    <div class="page-header">
      <h2>素材管理</h2>
      <a-space>
        <a-button type="primary" @click="showUploadModal = true">
          <UploadOutlined /> 上传素材
        </a-button>
        <a-button @click="showBatchUpload = true">
          <CloudUploadOutlined /> 批量上传
        </a-button>
      </a-space>
    </div>

    <!-- Search & Filter Bar -->
    <a-card class="filter-card" :bordered="false">
      <a-row :gutter="16">
        <a-col :span="6">
          <a-input-search
            v-model:value="searchKeyword"
            placeholder="搜索素材标题"
            @search="loadMaterials"
            allow-clear
          />
        </a-col>
        <a-col :span="4">
          <a-select
            v-model:value="filterStatus"
            placeholder="状态筛选"
            allow-clear
            style="width: 100%"
            @change="loadMaterials"
          >
            <a-select-option value="uploaded">已上传</a-select-option>
            <a-select-option value="parsing">解析中</a-select-option>
            <a-select-option value="parsed">已解析</a-select-option>
            <a-select-option value="vectorized">已向量化</a-select-option>
            <a-select-option value="failed">失败</a-select-option>
          </a-select>
        </a-col>
        <a-col :span="4">
          <a-select
            v-model:value="filterFormat"
            placeholder="格式筛选"
            allow-clear
            style="width: 100%"
            @change="loadMaterials"
          >
            <a-select-option value="pdf">PDF</a-select-option>
            <a-select-option value="word">Word</a-select-option>
            <a-select-option value="epub">EPUB</a-select-option>
            <a-select-option value="markdown">Markdown</a-select-option>
            <a-select-option value="image">图片</a-select-option>
            <a-select-option value="video">视频</a-select-option>
            <a-select-option value="audio">音频</a-select-option>
            <a-select-option value="csv">CSV</a-select-option>
          </a-select>
        </a-col>
        <a-col :span="4">
          <a-input
            v-model:value="filterCategory"
            placeholder="分类筛选"
            allow-clear
            @pressEnter="loadMaterials"
          />
        </a-col>
        <a-col :span="2">
          <a-button @click="resetFilters">重置</a-button>
        </a-col>
      </a-row>
    </a-card>

    <!-- Materials Table -->
    <a-card :bordered="false" style="margin-top: 16px">
      <a-table
        :columns="columns"
        :data-source="materials"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'title'">
            <a href="javascript:void(0)" @click="openMaterial(record)" style="color: #1677ff; font-weight: 500;">
              <FileTextOutlined style="margin-right: 4px" />{{ record.title }}
            </a>
          </template>
          <template v-if="column.key === 'format'">
            <a-tag :color="formatColors[record.format] || 'default'">
              {{ formatLabels[record.format] || record.format }}
            </a-tag>
          </template>
          <template v-if="column.key === 'status'">
            <a-tag :color="statusColors[record.status]">
              {{ statusLabels[record.status] || record.status }}
            </a-tag>
          </template>
          <template v-if="column.key === 'file_size'">
            {{ formatFileSize(record.file_size) }}
          </template>
          <template v-if="column.key === 'created_at'">
            {{ formatDate(record.created_at) }}
          </template>
          <template v-if="column.key === 'actions'">
            <a-space>
              <a-button size="small" @click="viewDetail(record)">详情</a-button>
              <a-button size="small" type="primary" ghost @click="downloadMaterial(record)">
                下载
              </a-button>
              <a-popconfirm title="确定删除此素材？" @confirm="deleteMaterial(record.id)">
                <a-button size="small" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Upload Modal -->
    <a-modal
      v-model:open="showUploadModal"
      title="上传素材"
      :footer="null"
      :width="520"
      @cancel="resetUploadForm"
    >
      <a-form :model="uploadForm" layout="vertical">
        <a-form-item label="素材标题" required>
          <a-input v-model:value="uploadForm.title" placeholder="请输入素材标题" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="uploadForm.description" :rows="3" placeholder="素材描述（可选）" />
        </a-form-item>
        <a-form-item label="分类">
          <a-input v-model:value="uploadForm.category" placeholder="素材分类（可选）" />
        </a-form-item>
        <a-form-item label="标签">
          <a-input v-model:value="uploadForm.tags" placeholder="多个标签用逗号分隔" />
        </a-form-item>
        <a-form-item label="选择文件" required>
          <a-upload
            :before-upload="handleBeforeUpload"
            :file-list="fileList"
            :max-count="1"
            @remove="fileList = []"
          >
            <a-button><UploadOutlined /> 选择文件</a-button>
          </a-upload>
          <div class="upload-hint">支持 PDF, Word, EPUB, Markdown, 图片, 视频, 音频, CSV, JSON</div>
        </a-form-item>
        <a-form-item>
          <a-button
            type="primary"
            :loading="uploading"
            :disabled="!uploadForm.title || fileList.length === 0"
            @click="handleUpload"
            block
          >
            上传
          </a-button>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- Batch Upload Modal -->
    <a-modal
      v-model:open="showBatchUpload"
      title="批量上传"
      :footer="null"
      :width="520"
    >
      <a-form layout="vertical">
        <a-form-item label="分类">
          <a-input v-model:value="batchCategory" placeholder="批量上传分类（可选）" />
        </a-form-item>
        <a-form-item label="选择文件">
          <a-upload-dragger
            :before-upload="handleBatchBeforeUpload"
            :file-list="batchFileList"
            multiple
            @remove="(file: any) => { batchFileList = batchFileList.filter((f: any) => f.uid !== file.uid) }"
          >
            <p class="ant-upload-drag-icon"><InboxOutlined /></p>
            <p class="ant-upload-text">点击或拖拽文件到此区域</p>
            <p class="ant-upload-hint">支持 PDF、Word、EPUB、Markdown、图片、视频、音频、CSV、JSON 批量上传</p>
          </a-upload-dragger>
        </a-form-item>
        <a-form-item>
          <a-button
            type="primary"
            :loading="uploading"
            :disabled="batchFileList.length === 0"
            @click="handleBatchUpload"
            block
          >
            批量上传 ({{ batchFileList.length }} 个文件)
          </a-button>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- Detail Drawer -->
    <a-drawer
      v-model:open="showDetail"
      title="素材详情"
      :width="560"
      placement="right"
    >
      <template v-if="currentMaterial">
        <a-descriptions :column="1" bordered size="small">
          <a-descriptions-item label="标题">{{ currentMaterial.title }}</a-descriptions-item>
          <a-descriptions-item label="格式">
            <a-tag :color="formatColors[currentMaterial.format]">
              {{ formatLabels[currentMaterial.format] }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="状态">
            <a-tag :color="statusColors[currentMaterial.status]">
              {{ statusLabels[currentMaterial.status] }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="大小">{{ formatFileSize(currentMaterial.file_size) }}</a-descriptions-item>
          <a-descriptions-item label="分类">{{ currentMaterial.category || '-' }}</a-descriptions-item>
          <a-descriptions-item label="标签">
            <template v-if="currentMaterial.tags?.length">
              <a-tag v-for="tag in currentMaterial.tags" :key="tag">{{ tag }}</a-tag>
            </template>
            <span v-else>-</span>
          </a-descriptions-item>
          <a-descriptions-item label="描述">{{ currentMaterial.description || '-' }}</a-descriptions-item>
          <a-descriptions-item label="上传时间">{{ formatDate(currentMaterial.created_at) }}</a-descriptions-item>
        </a-descriptions>

        <a-divider>知识单元</a-divider>
        <a-spin :spinning="loadingKnowledgeUnits">
          <template v-if="knowledgeUnits.length">
            <a-collapse>
              <a-collapse-panel
                v-for="unit in knowledgeUnits"
                :key="unit.id"
                :header="unit.title"
              >
                <p>{{ unit.content }}</p>
              </a-collapse-panel>
            </a-collapse>
          </template>
          <a-empty v-else description="暂无知识单元" />
        </a-spin>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import {
  UploadOutlined,
  CloudUploadOutlined,
  InboxOutlined,
  FileTextOutlined,
} from '@ant-design/icons-vue'
import request from '@/utils/request'

interface Material {
  id: string
  title: string
  description: string | null
  format: string
  file_path: string
  file_size: number
  status: string
  category: string | null
  tags: string[] | null
  source_url: string | null
  quality_score: number | null
  approved_question_count: number
  uploaded_by: string
  created_at: string
  updated_at: string
}

// Table columns
const columns = [
  { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
  { title: '格式', key: 'format', width: 100 },
  { title: '大小', key: 'file_size', width: 100 },
  { title: '状态', key: 'status', width: 100 },
  { title: '题目数量（已审核）', dataIndex: 'approved_question_count', key: 'approved_question_count', width: 140 },
  { title: '分类', dataIndex: 'category', key: 'category', width: 120 },
  { title: '上传时间', key: 'created_at', width: 160 },
  { title: '操作', key: 'actions', width: 200, fixed: 'right' as const },
]

const formatLabels: Record<string, string> = {
  pdf: 'PDF', word: 'Word', epub: 'EPUB', markdown: 'Markdown', html: 'HTML',
  image: '图片', video: '视频', audio: '音频', csv: 'CSV', json: 'JSON',
}
const formatColors: Record<string, string> = {
  pdf: 'red', word: 'blue', epub: 'volcano', markdown: 'green', html: 'orange',
  image: 'purple', video: 'cyan', audio: 'magenta', csv: 'geekblue', json: 'lime',
}
const statusLabels: Record<string, string> = {
  uploaded: '已上传', parsing: '解析中', parsed: '已解析', vectorized: '已向量化', failed: '失败',
}
const statusColors: Record<string, string> = {
  uploaded: 'default', parsing: 'processing', parsed: 'success', vectorized: 'blue', failed: 'error',
}

// State
const materials = ref<Material[]>([])
const loading = ref(false)
const searchKeyword = ref('')
const filterStatus = ref<string | undefined>(undefined)
const filterFormat = ref<string | undefined>(undefined)
const filterCategory = ref('')
const pagination = reactive({ current: 1, pageSize: 20, total: 0 })

// Upload state
const showUploadModal = ref(false)
const showBatchUpload = ref(false)
const uploading = ref(false)
const fileList = ref<any[]>([])
const batchFileList = ref<any[]>([])
const batchCategory = ref('')
const uploadForm = reactive({
  title: '',
  description: '',
  category: '',
  tags: '',
})

// Detail state
const showDetail = ref(false)
const currentMaterial = ref<Material | null>(null)
const knowledgeUnits = ref<any[]>([])
const loadingKnowledgeUnits = ref(false)

// Load materials
async function loadMaterials() {
  loading.value = true
  try {
    const params: any = {
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize,
    }
    if (searchKeyword.value) params.keyword = searchKeyword.value
    if (filterStatus.value) params.status = filterStatus.value
    if (filterFormat.value) params.format = filterFormat.value
    if (filterCategory.value) params.category = filterCategory.value

    const res: any = await request.get('/materials', { params })
    materials.value = res.data
    pagination.total = res.total
  } catch {
    // Error handled by interceptor
  } finally {
    loading.value = false
  }
}

function handleTableChange(pag: any) {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  loadMaterials()
}

function resetFilters() {
  searchKeyword.value = ''
  filterStatus.value = undefined
  filterFormat.value = undefined
  filterCategory.value = ''
  pagination.current = 1
  loadMaterials()
}

// Upload
function handleBeforeUpload(file: any) {
  fileList.value = [file]
  return false
}

function handleBatchBeforeUpload(file: any) {
  batchFileList.value = [...batchFileList.value, file]
  return false
}

function resetUploadForm() {
  uploadForm.title = ''
  uploadForm.description = ''
  uploadForm.category = ''
  uploadForm.tags = ''
  fileList.value = []
}

async function handleUpload() {
  if (!uploadForm.title || fileList.value.length === 0) return
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', fileList.value[0])
    formData.append('title', uploadForm.title)
    if (uploadForm.description) formData.append('description', uploadForm.description)
    if (uploadForm.category) formData.append('category', uploadForm.category)
    if (uploadForm.tags) formData.append('tags', uploadForm.tags)

    await request.post('/materials', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    })
    message.success('上传成功')
    showUploadModal.value = false
    resetUploadForm()
    loadMaterials()
  } catch {
    // Error handled by interceptor
  } finally {
    uploading.value = false
  }
}

async function handleBatchUpload() {
  if (batchFileList.value.length === 0) return
  uploading.value = true
  try {
    const formData = new FormData()
    batchFileList.value.forEach((file: any) => {
      formData.append('files', file)
    })
    if (batchCategory.value) formData.append('category', batchCategory.value)

    const res: any = await request.post('/materials/batch', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    })
    message.success(`成功上传 ${res.uploaded} 个文件${res.failed > 0 ? `，${res.failed} 个失败` : ''}`)
    showBatchUpload.value = false
    batchFileList.value = []
    batchCategory.value = ''
    loadMaterials()
  } catch {
    // Error handled by interceptor
  } finally {
    uploading.value = false
  }
}

// Open / Preview material in new tab
async function openMaterial(record: Material) {
  try {
    const res: any = await request.get(`/materials/${record.id}/download`)
    window.open(res.download_url, '_blank')
  } catch {
    message.error('打开素材失败')
  }
}

// Download
async function downloadMaterial(record: Material) {
  try {
    const res: any = await request.get(`/materials/${record.id}/download`)
    const link = document.createElement('a')
    link.href = res.download_url
    link.download = res.filename || record.title
    link.rel = 'noopener'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  } catch {
    message.error('获取下载链接失败')
  }
}

// Delete
async function deleteMaterial(id: string) {
  try {
    await request.delete(`/materials/${id}`)
    message.success('删除成功')
    loadMaterials()
  } catch {
    // Error handled by interceptor
  }
}

// Detail
async function viewDetail(record: Material) {
  currentMaterial.value = record
  showDetail.value = true
  loadKnowledgeUnits(record.id)
}

async function loadKnowledgeUnits(materialId: string) {
  loadingKnowledgeUnits.value = true
  try {
    const res: any = await request.get(`/materials/${materialId}/knowledge-units`)
    knowledgeUnits.value = res.units || []
  } catch {
    knowledgeUnits.value = []
  } finally {
    loadingKnowledgeUnits.value = false
  }
}

// Utility
function formatFileSize(bytes: number | null): string {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

onMounted(() => {
  loadMaterials()
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  color: var(--text-color);
}

.filter-card {
  margin-bottom: 0;
}

.upload-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-hint);
}
</style>
