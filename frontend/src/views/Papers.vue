<template>
  <div class="page-container">
    <div class="page-header">
      <h2>试卷管理</h2>
      <a-space>
        <a-button type="primary" @click="showCreateModal">
          <template #icon><PlusOutlined /></template>
          新建试卷
        </a-button>
        <a-button @click="importModal.visible = true">
          <template #icon><UploadOutlined /></template>
          导入试卷
        </a-button>
        <a-button @click="router.push('/papers/archive')">
          <template #icon><RestOutlined /></template>
          试卷归档
        </a-button>
      </a-space>
    </div>

    <!-- Filter Bar -->
    <a-card class="filter-card" :bordered="false">
      <a-row :gutter="16">
        <a-col :span="6">
          <a-input v-model:value="filters.keyword" placeholder="搜索试卷标题" allow-clear @press-enter="fetchPapers">
            <template #prefix><SearchOutlined /></template>
          </a-input>
        </a-col>
        <a-col :span="4">
          <a-select v-model:value="filters.status" placeholder="状态筛选" allow-clear style="width: 100%">
            <a-select-option value="draft">草稿</a-select-option>
            <a-select-option value="published">已发布</a-select-option>
          </a-select>
        </a-col>
        <a-col :span="4">
          <a-input v-model:value="filters.tag" placeholder="标签筛选" allow-clear @press-enter="fetchPapers" />
        </a-col>
        <a-col :span="4">
          <a-button type="primary" @click="fetchPapers">查询</a-button>
          <a-button style="margin-left: 8px" @click="resetFilters">重置</a-button>
        </a-col>
      </a-row>
    </a-card>

    <!-- Papers Table -->
    <a-card class="card-container" :bordered="false">
      <a-table
        :columns="columns"
        :data-source="papers"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
        :custom-row="customRow"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'title'">
            <a @click.stop="openDetail(record)" style="color: #1F4E79; font-weight: 500">{{ record.title }}</a>
          </template>
          <template v-if="column.key === 'status'">
            <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
          <template v-if="column.key === 'created_at'">
            {{ formatDate(record.created_at) }}
          </template>
          <template v-if="column.key === 'actions'">
            <a-space @click.stop>
              <a @click="goAssemble(record)" v-if="record.status === 'draft'">
                <EditOutlined /> {{ record.question_count > 0 ? '编辑试题' : '组卷' }}
              </a>
              <a-popconfirm title="确定发布此试卷？发布后试题内容将锁定。" @confirm="publishPaper(record)" v-if="record.status === 'draft' && record.question_count > 0">
                <a style="color: #52c41a">发布</a>
              </a-popconfirm>
              <a @click="duplicatePaper(record)">复制</a>
              <a-dropdown>
                <a>导出 <DownOutlined /></a>
                <template #overlay>
                  <a-menu>
                    <a-menu-item @click="exportPaper(record, 'json')">导出 JSON</a-menu-item>
                    <a-menu-item @click="exportPaper(record, 'docx')">导出 Word</a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
              <a-popconfirm title="删除后试卷将移入归档，可在「试卷归档」中恢复或彻底删除。" @confirm="softDeletePaper(record)">
                <a style="color: #ff4d4f">删除</a>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- ────────────────────────────────────────────────────────────────────── -->
    <!-- Paper Detail Drawer -->
    <!-- ────────────────────────────────────────────────────────────────────── -->
    <a-drawer
      v-model:open="detail.visible"
      :title="detail.data?.title || '试卷详情'"
      :width="800"
      :body-style="{ padding: '16px 24px' }"
    >
      <a-spin :spinning="detail.loading">
        <template v-if="detail.data">
          <!-- Header Info -->
          <div class="detail-header">
            <a-descriptions :column="2" bordered size="small">
              <a-descriptions-item label="状态">
                <a-tag :color="statusColor(detail.data.status)">{{ statusLabel(detail.data.status) }}</a-tag>
              </a-descriptions-item>
              <a-descriptions-item label="总分">{{ detail.data.total_score ?? 0 }} 分</a-descriptions-item>
              <a-descriptions-item label="时限">{{ detail.data.time_limit_minutes ? detail.data.time_limit_minutes + ' 分钟' : '不限时' }}</a-descriptions-item>
              <a-descriptions-item label="题目数">{{ allQuestions.length }} 题</a-descriptions-item>
              <a-descriptions-item label="标题" :span="2" v-if="isDraft">
                <a-input v-model:value="detail.data.title" size="small" @blur="saveMetaField('title', detail.data.title)" />
              </a-descriptions-item>
              <a-descriptions-item label="描述" :span="2">
                <template v-if="isDraft">
                  <a-textarea v-model:value="detail.data.description" :rows="2" size="small" @blur="saveMetaField('description', detail.data.description)" />
                </template>
                <template v-else>{{ detail.data.description || '无' }}</template>
              </a-descriptions-item>
            </a-descriptions>
          </div>

          <!-- Locked hint for non-draft -->
          <a-alert
            v-if="!isDraft"
            type="info"
            message="已发布/已归档试卷内容为只读。如需修改请「复制」为新草稿后编辑。"
            show-icon
            style="margin: 16px 0"
          />

          <!-- Draft toolbar -->
          <div v-if="isDraft" class="detail-toolbar">
            <a-button type="primary" size="small" @click="goAssemble(detail.data)">
              <EditOutlined /> 进入组卷编辑器
            </a-button>
            <a-button size="small" @click="openSyncPreview">
              <DatabaseOutlined /> 导入题库
            </a-button>
          </div>

          <!-- Non-draft can also sync to bank -->
          <div v-if="!isDraft && allQuestions.length > 0" class="detail-toolbar" style="background: #f6ffed; border-color: #b7eb8f">
            <a-button size="small" @click="openSyncPreview">
              <DatabaseOutlined /> 导入题库
            </a-button>
            <span style="font-size: 12px; color: #666">将试卷中的题目同步到题库，已在题库中的题目将自动跳过</span>
          </div>

          <!-- Question List by Section -->
          <div class="detail-sections">
            <template v-for="section in detail.data.sections" :key="section.id">
              <div class="section-block">
                <div class="section-title-row">
                  <h4 class="section-title">{{ section.title || '未命名分节' }}</h4>
                  <span class="section-meta">{{ section.questions.length }} 题 / {{ sectionScore(section) }} 分</span>
                </div>
                <a-table
                  :columns="qColumns"
                  :data-source="section.questions"
                  :pagination="false"
                  size="small"
                  row-key="id"
                  :bordered="true"
                >
                  <template #bodyCell="{ column, record, index }">
                    <template v-if="column.key === 'order'">{{ index + 1 }}</template>
                    <template v-if="column.key === 'type'">
                      <a-tag :color="typeColor(record.question?.question_type)">{{ typeLabel(record.question?.question_type) }}</a-tag>
                    </template>
                    <template v-if="column.key === 'stem'">
                      <div class="stem-cell">
                        {{ record.stem_override || record.question?.stem || '-' }}
                        <a-tooltip v-if="record.stem_override" title="题干已修改（与题库原题不同）">
                          <span class="override-badge">改</span>
                        </a-tooltip>
                      </div>
                    </template>
                    <template v-if="column.key === 'answer'">
                      <span class="answer-text">{{ record.question?.correct_answer || '-' }}</span>
                    </template>
                    <template v-if="column.key === 'score'">
                      <template v-if="isDraft">
                        <a-input-number
                          :value="record.score"
                          :min="0" :max="100" size="small" style="width: 70px"
                          @change="(val: number) => updateQuestionScore(record.id, val)"
                        />
                      </template>
                      <template v-else>{{ record.score }} 分</template>
                    </template>
                    <template v-if="column.key === 'bank_status'">
                      <a-tooltip :title="bankStatusTip(record)">
                        <a-tag :color="record.question?.status === 'approved' && !record.stem_override && !record.options_override ? 'green' : 'orange'" style="font-size: 11px">
                          {{ bankStatusText(record) }}
                        </a-tag>
                      </a-tooltip>
                    </template>
                    <template v-if="column.key === 'actions'">
                      <a-popconfirm v-if="isDraft" title="确定移除此题？" @confirm="removeQuestion(record.id)">
                        <a style="color: #ff4d4f" size="small"><DeleteOutlined /></a>
                      </a-popconfirm>
                    </template>
                  </template>
                </a-table>
              </div>
            </template>

            <!-- Unsectioned Questions -->
            <div v-if="detail.data.unsectioned_questions?.length > 0" class="section-block">
              <div class="section-title-row">
                <h4 class="section-title">未分节题目</h4>
                <span class="section-meta">{{ detail.data.unsectioned_questions.length }} 题</span>
              </div>
              <a-table
                :columns="qColumns"
                :data-source="detail.data.unsectioned_questions"
                :pagination="false"
                size="small"
                row-key="id"
                :bordered="true"
              >
                <template #bodyCell="{ column, record, index }">
                  <template v-if="column.key === 'order'">{{ index + 1 }}</template>
                  <template v-if="column.key === 'type'">
                    <a-tag :color="typeColor(record.question?.question_type)">{{ typeLabel(record.question?.question_type) }}</a-tag>
                  </template>
                  <template v-if="column.key === 'stem'">
                    <div class="stem-cell">
                      {{ record.stem_override || record.question?.stem || '-' }}
                      <a-tooltip v-if="record.stem_override" title="题干已修改（与题库原题不同）">
                        <span class="override-badge">改</span>
                      </a-tooltip>
                    </div>
                  </template>
                  <template v-if="column.key === 'answer'">
                    <span class="answer-text">{{ record.question?.correct_answer || '-' }}</span>
                  </template>
                  <template v-if="column.key === 'score'">
                    <template v-if="isDraft">
                      <a-input-number
                        :value="record.score"
                        :min="0" :max="100" size="small" style="width: 70px"
                        @change="(val: number) => updateQuestionScore(record.id, val)"
                      />
                    </template>
                    <template v-else>{{ record.score }} 分</template>
                  </template>
                  <template v-if="column.key === 'bank_status'">
                    <a-tooltip :title="bankStatusTip(record)">
                      <a-tag :color="record.question?.status === 'approved' && !record.stem_override && !record.options_override ? 'green' : 'orange'" style="font-size: 11px">
                        {{ bankStatusText(record) }}
                      </a-tag>
                    </a-tooltip>
                  </template>
                  <template v-if="column.key === 'actions'">
                    <a-popconfirm v-if="isDraft" title="确定移除此题？" @confirm="removeQuestion(record.id)">
                      <a style="color: #ff4d4f" size="small"><DeleteOutlined /></a>
                    </a-popconfirm>
                  </template>
                </template>
              </a-table>
            </div>

            <a-empty v-if="allQuestions.length === 0" description="暂无题目" />
          </div>
        </template>
      </a-spin>
    </a-drawer>

    <!-- Sync to Bank Modal -->
    <a-modal
      v-model:open="syncModal.visible"
      title="导入题库 — 比对预览"
      :width="780"
      :footer="null"
      :destroy-on-close="true"
    >
      <a-spin :spinning="syncModal.loading">
        <div v-if="syncModal.preview" class="sync-preview">
          <a-alert
            style="margin-bottom: 16px"
            :type="syncModal.preview.to_import > 0 ? 'info' : 'success'"
            show-icon
          >
            <template #message>
              <span v-if="syncModal.preview.to_import > 0">
                共 {{ syncModal.preview.total }} 题：
                <strong>{{ syncModal.preview.to_import }}</strong> 题可导入题库，
                {{ syncModal.preview.already_in_bank }} 题已在题库中
              </span>
              <span v-else>所有 {{ syncModal.preview.total }} 题均已在题库中，无需导入</span>
            </template>
          </a-alert>

          <a-table
            :columns="syncColumns"
            :data-source="syncModal.preview.items"
            :pagination="false"
            size="small"
            row-key="pq_id"
            :bordered="true"
            :row-selection="syncModal.preview.to_import > 0 ? { selectedRowKeys: syncModal.selectedKeys, onChange: onSyncSelectChange, getCheckboxProps: getSyncCheckboxProps } : undefined"
            :scroll="{ y: 360 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'stem'">
                <div class="stem-cell">{{ record.stem }}</div>
              </template>
              <template v-if="column.key === 'question_type'">
                <a-tag :color="typeColor(record.question_type)" style="font-size: 11px">{{ typeLabel(record.question_type) }}</a-tag>
              </template>
              <template v-if="column.key === 'status'">
                <a-tag :color="syncStatusColor(record.status)">{{ syncStatusLabel(record.status) }}</a-tag>
              </template>
              <template v-if="column.key === 'action'">
                <span :style="{ color: syncActionColor(record.action) }">{{ syncActionLabel(record.action) }}</span>
              </template>
              <template v-if="column.key === 'reason'">
                <span style="font-size: 12px; color: #999">{{ record.reason }}</span>
              </template>
            </template>
          </a-table>

          <div class="sync-footer" v-if="syncModal.preview.to_import > 0">
            <a-button
              type="primary"
              :loading="syncModal.executing"
              :disabled="syncModal.selectedKeys.length === 0"
              @click="executeSyncToBank"
            >
              确认导入（{{ syncModal.selectedKeys.length }} 题）
            </a-button>
            <a-button @click="syncModal.visible = false">取消</a-button>
          </div>
          <div class="sync-footer" v-else>
            <a-button type="primary" @click="syncModal.visible = false">确定</a-button>
          </div>
        </div>
      </a-spin>
    </a-modal>

    <!-- Create Modal -->
    <a-modal
      v-model:open="createModal.visible"
      title="新建试卷"
      @ok="handleCreate"
      :confirm-loading="createModal.loading"
    >
      <a-form :model="createModal.data" layout="vertical">
        <a-form-item label="标题" required>
          <a-input v-model:value="createModal.data.title" placeholder="请输入试卷标题" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="createModal.data.description" placeholder="请输入试卷描述（可选）" :rows="3" />
        </a-form-item>
        <a-form-item label="时间限制（分钟）">
          <a-input-number v-model:value="createModal.data.time_limit_minutes" :min="1" :max="300" placeholder="不限时" style="width: 100%" />
        </a-form-item>
        <a-form-item label="标签">
          <a-input v-model:value="createModal.data.tags" placeholder="多个标签用逗号分隔（可选）" />
        </a-form-item>
      </a-form>
      <div class="modal-hint">创建后将自动进入组卷页面，可手动添加题目或使用智能组卷。</div>
    </a-modal>

    <!-- Import Modal -->
    <a-modal
      v-model:open="importModal.visible"
      title="导入试卷"
      :footer="null"
      :width="480"
    >
      <a-form layout="vertical">
        <a-form-item label="选择试卷文件" required>
          <a-upload
            :before-upload="handleImportBeforeUpload"
            :file-list="importModal.fileList"
            :max-count="1"
            accept=".json,.docx"
            @remove="importModal.fileList = []"
          >
            <a-button><UploadOutlined /> 选择文件</a-button>
          </a-upload>
          <div class="upload-hint">支持 Word (.docx) 和 JSON 格式文件</div>
        </a-form-item>
        <a-form-item>
          <a-button
            type="primary"
            :loading="importModal.loading"
            :disabled="importModal.fileList.length === 0"
            @click="handleImport"
            block
          >
            导入
          </a-button>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { PlusOutlined, SearchOutlined, UploadOutlined, DownOutlined, EditOutlined, DeleteOutlined, RestOutlined, DatabaseOutlined } from '@ant-design/icons-vue'
import request from '@/utils/request'

const router = useRouter()

const loading = ref(false)
const papers = ref<any[]>([])
const filters = reactive({ keyword: '', status: undefined as string | undefined, tag: '' })
const pagination = reactive({ current: 1, pageSize: 20, total: 0 })

const columns = [
  { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
  { title: '状态', key: 'status', width: 100 },
  { title: '总分', dataIndex: 'total_score', key: 'total_score', width: 80 },
  { title: '题目数', dataIndex: 'question_count', key: 'question_count', width: 80 },
  { title: '引用次数', dataIndex: 'usage_count', key: 'usage_count', width: 90 },
  { title: '创建时间', key: 'created_at', width: 160 },
  { title: '操作', key: 'actions', width: 300, fixed: 'right' },
]

// Detail drawer question columns
const qColumns = computed(() => {
  const base = [
    { title: '序号', key: 'order', width: 55 },
    { title: '题型', key: 'type', width: 80 },
    { title: '题目', key: 'stem', ellipsis: true },
    { title: '答案', key: 'answer', width: 100, ellipsis: true },
    { title: '分值', key: 'score', width: 80 },
    { title: '题库', key: 'bank_status', width: 65 },
  ]
  if (isDraft.value) {
    base.push({ title: '', key: 'actions', width: 50 })
  }
  return base
})

// ── Detail Drawer ─────────────────────────────────────────────────────────

const detail = reactive({
  visible: false,
  loading: false,
  data: null as any,
})

const isDraft = computed(() => detail.data?.status === 'draft')

const allQuestions = computed(() => {
  if (!detail.data) return []
  const qs: any[] = []
  for (const sec of (detail.data.sections || [])) {
    qs.push(...(sec.questions || []))
  }
  qs.push(...(detail.data.unsectioned_questions || []))
  return qs
})

function sectionScore(section: any) {
  return (section.questions || []).reduce((sum: number, q: any) => sum + (q.score || 0), 0)
}

function customRow(record: any) {
  return {
    style: { cursor: 'pointer' },
    onClick: () => openDetail(record),
  }
}

async function openDetail(record: any) {
  detail.visible = true
  detail.loading = true
  detail.data = null
  try {
    const data: any = await request.get(`/papers/${record.id}`)
    detail.data = data
  } catch { /* handled */ } finally {
    detail.loading = false
  }
}

// Save a single meta field inline (draft only)
async function saveMetaField(field: string, value: any) {
  if (!detail.data || !isDraft.value) return
  try {
    await request.put(`/papers/${detail.data.id}`, { [field]: value })
  } catch { /* silent */ }
}

// Update question score inline (draft only)
async function updateQuestionScore(pqId: string, score: number) {
  if (!isDraft.value) return
  try {
    await request.put(`/papers/questions/${pqId}`, { score })
    // Update local state
    for (const sec of (detail.data.sections || [])) {
      for (const q of (sec.questions || [])) {
        if (q.id === pqId) { q.score = score; return }
      }
    }
    for (const q of (detail.data.unsectioned_questions || [])) {
      if (q.id === pqId) { q.score = score; return }
    }
  } catch { message.error('更新分值失败') }
}

// Remove question (draft only)
async function removeQuestion(pqId: string) {
  if (!isDraft.value || !detail.data) return
  try {
    await request.delete(`/papers/questions/${pqId}`)
    message.success('已移除')
    // Reload detail
    const data: any = await request.get(`/papers/${detail.data.id}`)
    detail.data = data
    fetchPapers()
  } catch { message.error('移除失败') }
}

// ── Sync to Bank ─────────────────────────────────────────────────────────

const syncModal = reactive({
  visible: false,
  loading: false,
  executing: false,
  preview: null as any,
  selectedKeys: [] as string[],
})

const syncColumns = [
  { title: '题目', key: 'stem', ellipsis: true },
  { title: '题型', key: 'question_type', width: 70 },
  { title: '当前状态', key: 'status', width: 100 },
  { title: '操作', key: 'action', width: 100 },
  { title: '说明', key: 'reason', ellipsis: true, width: 200 },
]

function syncStatusColor(s: string) {
  return { in_bank: 'green', draft_in_bank: 'orange', has_override: 'blue', missing: 'red' }[s] || 'default'
}
function syncStatusLabel(s: string) {
  return { in_bank: '已在题库', draft_in_bank: '草稿', has_override: '已修改', missing: '缺失' }[s] || s
}
function syncActionColor(a: string) {
  return { skip: '#999', create_new: '#1890ff', promote: '#52c41a' }[a] || '#999'
}
function syncActionLabel(a: string) {
  return { skip: '跳过', create_new: '新建入库', promote: '提升状态' }[a] || a
}

function onSyncSelectChange(keys: string[]) {
  syncModal.selectedKeys = keys
}
function getSyncCheckboxProps(record: any) {
  return { disabled: record.action === 'skip' }
}

async function openSyncPreview() {
  if (!detail.data) return
  syncModal.visible = true
  syncModal.loading = true
  syncModal.preview = null
  syncModal.selectedKeys = []
  try {
    const data: any = await request.get(`/papers/${detail.data.id}/sync-to-bank/preview`)
    syncModal.preview = data
    // Auto-select all importable items
    syncModal.selectedKeys = (data.items || [])
      .filter((it: any) => it.action !== 'skip')
      .map((it: any) => it.pq_id)
  } catch {
    message.error('获取比对预览失败')
    syncModal.visible = false
  } finally {
    syncModal.loading = false
  }
}

async function executeSyncToBank() {
  if (!detail.data || syncModal.selectedKeys.length === 0) return
  syncModal.executing = true
  try {
    const result: any = await request.post(`/papers/${detail.data.id}/sync-to-bank`, {
      pq_ids: syncModal.selectedKeys,
    })
    const msgs = []
    if (result.created > 0) msgs.push(`新建 ${result.created} 题`)
    if (result.promoted > 0) msgs.push(`提升 ${result.promoted} 题`)
    message.success(`导入完成：${msgs.join('，')}`)
    syncModal.visible = false
    // Refresh detail to show updated question_ids
    openDetail(detail.data)
  } catch {
    message.error('导入失败')
  } finally {
    syncModal.executing = false
  }
}

// ── Create Modal ──────────────────────────────────────────────────────────

const createModal = reactive({
  visible: false,
  loading: false,
  data: { title: '', description: '', time_limit_minutes: null as number | null, tags: '' },
})

function showCreateModal() {
  createModal.data = { title: '', description: '', time_limit_minutes: null, tags: '' }
  createModal.visible = true
}

async function handleCreate() {
  if (!createModal.data.title) {
    message.warning('请输入试卷标题')
    return
  }
  createModal.loading = true
  try {
    const payload: any = {
      title: createModal.data.title,
      description: createModal.data.description || undefined,
      time_limit_minutes: createModal.data.time_limit_minutes || undefined,
      tags: createModal.data.tags ? createModal.data.tags.split(',').map((t: string) => t.trim()).filter(Boolean) : undefined,
    }
    const data: any = await request.post('/papers', payload)
    message.success('创建成功，进入组卷页面')
    createModal.visible = false
    router.push(`/papers/${data.id}/edit`)
  } catch { /* handled */ } finally {
    createModal.loading = false
  }
}

// ── 组卷 / 编辑试题（跳转 PaperEditor）─────────────────────────────────

function goAssemble(record: any) {
  detail.visible = false
  router.push(`/papers/${record.id}/edit`)
}

// ── Import Modal ──────────────────────────────────────────────────────────

const importModal = reactive({
  visible: false,
  loading: false,
  fileList: [] as any[],
})

function handleImportBeforeUpload(file: any) {
  importModal.fileList = [file]
  return false
}

async function handleImport() {
  if (importModal.fileList.length === 0) return
  importModal.loading = true
  try {
    const file = importModal.fileList[0]
    const formData = new FormData()
    formData.append('file', file)
    const data: any = await request.post('/papers/import-file', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    importModal.visible = false
    importModal.fileList = []
    await fetchPapers()
    // Auto-open the imported paper's detail
    if (data && data.id) {
      message.success(`导入成功：「${data.title || '试卷'}」，已打开详情`)
      openDetail({ id: data.id })
    } else {
      message.success('导入成功')
    }
  } catch { /* handled by interceptor */ } finally {
    importModal.loading = false
  }
}

// ── Table & Helpers ───────────────────────────────────────────────────────

function statusColor(s: string) {
  return { draft: 'blue', published: 'green', archived: 'default' }[s] || 'default'
}
function statusLabel(s: string) {
  return { draft: '草稿', published: '已发布', archived: '已归档' }[s] || s
}
function typeLabel(t: string) {
  return { single_choice: '单选', multiple_choice: '多选', true_false: '判断', fill_blank: '填空', short_answer: '简答' }[t] || t || '-'
}
function typeColor(t: string) {
  return { single_choice: 'blue', multiple_choice: 'purple', true_false: 'cyan', fill_blank: 'orange', short_answer: 'green' }[t] || 'default'
}
function formatDate(d: string) {
  if (!d) return ''
  return new Date(d).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function bankStatusText(record: any) {
  const hasOverride = record.stem_override || record.options_override
  if (hasOverride) return '已修改'
  const status = record.question?.status
  if (status === 'approved') return '已入库'
  if (status === 'draft') return '草稿'
  if (status === 'pending_review') return '待审'
  return '未知'
}
function bankStatusTip(record: any) {
  const hasOverride = record.stem_override || record.options_override
  if (hasOverride) return `题目在试卷中被修改，可通过「导入题库」创建为新题目（题库ID: ${record.question_id?.slice(0, 8)}...）`
  const status = record.question?.status
  if (status === 'approved') return `已在题库中（ID: ${record.question_id?.slice(0, 8)}...）`
  return `题库状态: ${status}，可通过「导入题库」提升为已审核（ID: ${record.question_id?.slice(0, 8)}...）`
}

async function fetchPapers() {
  loading.value = true
  try {
    const params: any = { skip: (pagination.current - 1) * pagination.pageSize, limit: pagination.pageSize }
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.status) params.status = filters.status
    if (filters.tag) params.tag = filters.tag
    const data: any = await request.get('/papers', { params })
    papers.value = data.data || []
    pagination.total = data.total || 0
  } catch { /* handled by interceptor */ } finally {
    loading.value = false
  }
}

function handleTableChange(pag: any) {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  fetchPapers()
}

function resetFilters() {
  filters.keyword = ''
  filters.status = undefined
  filters.tag = ''
  pagination.current = 1
  fetchPapers()
}

// ── Lifecycle Actions ─────────────────────────────────────────────────────

async function publishPaper(record: any) {
  try {
    await request.post(`/papers/${record.id}/publish`)
    message.success('发布成功')
    fetchPapers()
    // If detail is open for this paper, refresh it
    if (detail.visible && detail.data?.id === record.id) {
      openDetail(record)
    }
  } catch { /* handled */ }
}

async function softDeletePaper(record: any) {
  try {
    await request.post(`/papers/${record.id}/archive`)
    message.success('已移入归档')
    if (detail.visible && detail.data?.id === record.id) {
      detail.visible = false
    }
    fetchPapers()
  } catch { /* handled */ }
}

async function duplicatePaper(record: any) {
  try {
    await request.post(`/papers/${record.id}/duplicate`)
    message.success('已复制为新草稿')
    fetchPapers()
  } catch { /* handled */ }
}

// ── Export ─────────────────────────────────────────────────────────────────

async function exportPaper(record: any, format: 'json' | 'docx' = 'json') {
  try {
    if (format === 'docx') {
      const token = localStorage.getItem('token')
      const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
      const resp = await fetch(`${baseURL}/papers/${record.id}/export?format=docx`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!resp.ok) throw new Error('导出失败')
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${record.title || 'paper'}.docx`
      link.click()
      URL.revokeObjectURL(url)
    } else {
      const data: any = await request.get(`/papers/${record.id}/export`)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${record.title || 'paper'}.json`
      link.click()
      URL.revokeObjectURL(url)
    }
    message.success('导出成功')
  } catch { /* handled */ }
}

onMounted(() => { fetchPapers() })
</script>

<style scoped>
.filter-card { margin-bottom: 16px; }

.upload-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-hint);
}

.modal-hint {
  margin-top: 12px;
  padding: 10px 12px;
  background: #f6f8fa;
  border-radius: 6px;
  font-size: 13px;
  color: #666;
}

/* Detail Drawer */
.detail-header {
  margin-bottom: 12px;
}

.detail-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 16px 0;
  padding: 12px 16px;
  background: #f0f7ff;
  border-radius: 6px;
  border: 1px dashed #91caff;
}

.detail-sections {
  margin-top: 16px;
}

.section-block {
  margin-bottom: 20px;
}

.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 4px;
}

.section-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #1F4E79;
}

.section-meta {
  font-size: 12px;
  color: #999;
}

.stem-cell {
  max-height: 40px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 20px;
}

.answer-text {
  font-family: 'Courier New', monospace;
  color: #52c41a;
  font-weight: 500;
}

.override-badge {
  display: inline-block;
  font-size: 10px;
  background: #e6f4ff;
  color: #1677ff;
  border: 1px solid #91caff;
  border-radius: 3px;
  padding: 0 3px;
  margin-left: 4px;
  line-height: 16px;
  vertical-align: middle;
}

/* Sync to Bank Modal */
.sync-preview {
  min-height: 200px;
}

.sync-footer {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #f0f0f0;
}
</style>
