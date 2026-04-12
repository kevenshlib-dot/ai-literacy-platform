<template>
  <div class="page-container">
    <div class="page-header">
      <h2>系统管理</h2>
      <p class="sub-title">平台级管理功能</p>
    </div>

    <a-tabs v-model:activeKey="activeTab" class="main-tabs">
      <!-- ══════════════════════════════════════════════════════ 模型配置 tab -->
      <a-tab-pane key="llm" tab="模型配置">

        <!-- ── 阶段一：模型提供方 ──────────────────────────────────────────── -->
        <div class="section">
          <div class="section-header">
            <div>
              <span class="section-title">第一步 &nbsp;配置模型提供方</span>
              <span class="section-hint">设置 API 密钥与服务地址，每条配置可独立测试</span>
            </div>
            <a-button type="primary" @click="openProviderModal()">
              + 添加提供方
            </a-button>
          </div>

          <a-spin :spinning="loadingProviders">
            <a-empty v-if="providers.length === 0" description="暂无配置，点击「添加提供方」开始" />

            <div v-else class="provider-list">
              <div v-for="p in providers" :key="p.id" class="provider-card" :class="{ disabled: !p.enabled }">
                <div class="provider-left">
                  <a-tag :color="typeColor(p.provider_type)" class="type-tag">{{ typeLabel(p.provider_type) }}</a-tag>
                  <span class="provider-name">{{ p.name }}</span>
                  <span class="provider-meta">{{ p.base_url }}</span>
                  <span class="provider-model">{{ p.model }}</span>
                </div>
                <div class="provider-right">
                  <a-tag v-if="!p.enabled" color="default">已停用</a-tag>
                  <a-button size="small" @click="testProvider(p)">测试</a-button>
                  <a-button size="small" @click="openProviderModal(p)">编辑</a-button>
                  <a-popconfirm title="确认删除此提供方？" @confirm="deleteProvider(p.id)">
                    <a-button size="small" danger>删除</a-button>
                  </a-popconfirm>
                </div>
              </div>
            </div>
          </a-spin>
        </div>

        <!-- ── 阶段二：模块分配 ────────────────────────────────────────────── -->
        <div class="section">
          <div class="section-header">
            <div>
              <span class="section-title">第二步 &nbsp;为各模块分配模型</span>
              <span class="section-hint">从已配置的提供方中选择，未分配的模块将使用 .env 默认值</span>
            </div>
            <a-button type="primary" :loading="savingAssignments" @click="saveAssignments">
              保存分配
            </a-button>
          </div>

          <a-spin :spinning="loadingAssignments">
            <div class="assignment-table">
              <div v-for="mod in modules" :key="mod.key" class="assignment-row">
                <div class="assignment-label">
                  <span class="mod-name">{{ mod.label }}</span>
                  <span class="mod-desc">{{ mod.desc }}</span>
                </div>
                <div class="assignment-select">
                  <a-select
                    v-model:value="assignments[mod.key]"
                    placeholder="— 使用 .env 默认值 —"
                    allow-clear
                    style="width: 280px"
                  >
                    <a-select-option v-for="p in enabledProviders" :key="p.id" :value="p.id">
                      <a-tag :color="typeColor(p.provider_type)" style="margin-right:6px;font-size:11px">
                        {{ typeLabel(p.provider_type) }}
                      </a-tag>
                      {{ p.name }} &nbsp;<span style="color:#999;font-size:12px">{{ p.model }}</span>
                    </a-select-option>
                  </a-select>
                </div>
                <div class="assignment-test">
                  <a-button
                    size="small"
                    :loading="testingModule === mod.key"
                    :disabled="!assignments[mod.key]"
                    @click="testAssignment(mod.key)"
                  >
                    测试
                  </a-button>
                  <a-tag v-if="assignmentResults[mod.key]" :color="assignmentResults[mod.key].success ? 'success' : 'error'" style="margin-left:8px">
                    {{ assignmentResults[mod.key].success ? '✓ 连通' : '✗ 失败' }}
                  </a-tag>
                </div>
              </div>
            </div>
          </a-spin>
        </div>

      </a-tab-pane>

      <a-tab-pane key="about" tab="平台信息" disabled />
    </a-tabs>

    <!-- ══════════════════════════════════════════════════════ 添加/编辑弹窗 -->
    <a-modal
      v-model:open="modalVisible"
      :title="editingProvider ? '编辑提供方' : '添加提供方'"
      width="580px"
      :confirm-loading="savingProvider"
      @ok="submitProvider"
    >
      <a-form :model="form" layout="vertical" style="margin-top:8px">

        <!-- 类型 + 名称 -->
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="提供方类型" required>
              <a-select v-model:value="form.provider_type" @change="onTypeChange">
                <a-select-opt-group label="☁️ 云端 API">
                  <a-select-option value="openai">OpenAI</a-select-option>
                  <a-select-option value="anthropic">Anthropic (Claude)</a-select-option>
                  <a-select-option value="google">Google AI (Gemini)</a-select-option>
                  <a-select-option value="deepseek">DeepSeek</a-select-option>
                  <a-select-option value="doubao">豆包（字节跳动）</a-select-option>
                  <a-select-option value="qwen">千问（阿里云）</a-select-option>
                  <a-select-option value="zhipu">智谱 AI（GLM）</a-select-option>
                  <a-select-option value="spark">讯飞星火</a-select-option>
                </a-select-opt-group>
                <a-select-opt-group label="🖥️ 本地服务">
                  <a-select-option value="vllm">vLLM</a-select-option>
                  <a-select-option value="ollama">Ollama</a-select-option>
                  <a-select-option value="lmstudio">LM Studio</a-select-option>
                  <a-select-option value="custom">自定义（OpenAI 兼容）</a-select-option>
                </a-select-opt-group>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="显示名称" required>
              <a-input v-model:value="form.name" placeholder="例：生产 GPT-4o" />
            </a-form-item>
          </a-col>
        </a-row>

        <!-- Base URL：仅本地服务显示 -->
        <a-form-item v-if="isLocalProvider" label="服务地址（Base URL）" required>
          <a-input v-model:value="form.base_url" :placeholder="TYPE_META[form.provider_type]?.base_url || 'http://host:port/v1'" />
          <div class="field-hint">填写 IP + 端口，例如 <code>http://192.168.1.10:8080/v1</code></div>
        </a-form-item>

        <!-- API Key -->
        <a-form-item :label="isLocalProvider ? 'API Key（可留空）' : 'API Key'" required>
          <a-input-password v-model:value="form.api_key" placeholder="sk-..." />
          <div class="field-hint">
            <span v-if="isLocalProvider">本地服务通常无需 API Key</span>
            <span v-else>
              存入数据库，优先级高于 <code>.env</code>；未分配模块时才使用 <code>.env</code> 兜底
            </span>
          </div>
        </a-form-item>

        <!-- 模型选择：云端用下拉（有预设列表），本地用输入框+刷新 -->
        <a-form-item label="模型" required>

          <!-- 云端且有预设 -->
          <a-select
            v-if="!isLocalProvider && presetModels.length > 0"
            v-model:value="form.model"
            show-search
            placeholder="选择模型"
            :options="presetModels.map(m => ({ value: m, label: m }))"
            :get-popup-container="(trigger: HTMLElement) => trigger.parentElement || document.body"
          />

          <!-- 云端但无预设（如豆包端点 ID） -->
          <a-input
            v-else-if="!isLocalProvider"
            v-model:value="form.model"
            :placeholder="modelPlaceholder"
          />

          <!-- 本地服务：输入框 + 获取按钮 -->
          <template v-else>
            <a-input-group compact>
              <a-select
                v-if="fetchedModels.length > 0"
                v-model:value="form.model"
                show-search
                placeholder="选择或输入模型"
                style="width: calc(100% - 90px)"
                :options="fetchedModels.map(m => ({ value: m, label: m }))"
                :get-popup-container="(trigger: HTMLElement) => trigger.parentElement || document.body"
              />
              <a-input
                v-else
                v-model:value="form.model"
                :placeholder="modelPlaceholder"
                style="width: calc(100% - 90px)"
              />
              <a-button
                style="width:86px"
                :loading="fetchingModels"
                @click="fetchModels"
              >
                获取模型
              </a-button>
            </a-input-group>
            <div class="field-hint">点击「获取模型」自动从本地服务拉取可用模型列表</div>
          </template>

        </a-form-item>

        <!-- 状态 + 测试 -->
        <a-row :gutter="16" align="middle">
          <a-col :span="10">
            <a-form-item label="状态">
              <a-switch v-model:checked="form.enabled" checked-children="启用" un-checked-children="停用" />
            </a-form-item>
          </a-col>
          <a-col :span="14" style="padding-top:28px">
            <a-button :loading="testingInModal" @click="testInModal">测试连接</a-button>
            <a-tag v-if="modalTestResult" :color="modalTestResult.success ? 'success' : 'error'" style="margin-left:8px">
              {{ modalTestResult.success ? `✓ ${modalTestResult.model}` : `✗ ${modalTestResult.error}` }}
            </a-tag>
          </a-col>
        </a-row>

      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import request from '@/utils/request'

// ── Provider type metadata ───────────────────────────────────────────────────
const TYPE_META: Record<string, { label: string; color: string; base_url: string; models: string[]; placeholder: string }> = {
  openai:    { label: 'OpenAI',      color: 'green',   base_url: 'https://api.openai.com/v1/',                             models: ['gpt-4o', 'gpt-4o-mini', 'o3', 'o4-mini'],                       placeholder: 'gpt-4o' },
  anthropic: { label: 'Anthropic',   color: 'purple',  base_url: 'https://api.anthropic.com/v1/',                          models: ['claude-opus-4-5', 'claude-sonnet-4-5', 'claude-haiku-4-5'],    placeholder: 'claude-sonnet-4-5' },
  google:    { label: 'Google AI',   color: 'blue',    base_url: 'https://generativelanguage.googleapis.com/v1beta/openai/', models: ['gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.0-flash-lite-001'],        placeholder: 'gemini-2.5-flash' },
  deepseek:  { label: 'DeepSeek',   color: 'cyan',    base_url: 'https://api.deepseek.com/v1/',                            models: ['deepseek-chat', 'deepseek-reasoner'],                           placeholder: 'deepseek-chat' },
  doubao:    { label: '豆包',        color: 'orange',  base_url: 'https://ark.cn-beijing.volces.com/api/v3/',              models: [],                                                                placeholder: 'ep-xxxxxxxx' },
  qwen:      { label: '千问',        color: 'gold',    base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1/',     models: ['qwen-max', 'qwen-plus', 'qwen-turbo', 'qwen2.5-72b-instruct'], placeholder: 'qwen-max' },
  zhipu:     { label: '智谱 AI',     color: 'magenta', base_url: 'https://open.bigmodel.cn/api/paas/v4/',                  models: ['glm-4-plus', 'glm-4-air', 'glm-4-flash'],                       placeholder: 'glm-4-air' },
  spark:     { label: '星火',        color: 'volcano', base_url: 'https://spark-api-open.xf-yun.com/v1/',                 models: ['lite', 'pro', 'max', '4.0Ultra'],                                placeholder: 'max' },
  vllm:      { label: 'vLLM',        color: 'default', base_url: 'http://192.168.x.x:8001/v1',                           models: [],                                                                placeholder: 'meta-llama/Llama-3-8B-Instruct' },
  ollama:    { label: 'Ollama',      color: 'default', base_url: 'http://localhost:11434/v1',                              models: [],                                                                placeholder: 'qwen2.5:7b' },
  lmstudio:  { label: 'LM Studio',  color: 'default', base_url: 'http://localhost:1234/v1',                               models: [],                                                                placeholder: 'local-model' },
  custom:    { label: '自定义',       color: 'default', base_url: '',                                                       models: [],                                                                placeholder: '模型名称' },
}

const localTypes = ['vllm', 'ollama', 'lmstudio', 'custom']

function typeLabel(t: string) { return TYPE_META[t]?.label ?? t }
function typeColor(t: string) { return TYPE_META[t]?.color ?? 'default' }

const isLocalProvider = computed(() => localTypes.includes(form.provider_type))

// ── Module definitions ────────────────────────────────────────────────────────
const modules = [
  { key: 'question_generation', label: '题目生成',  desc: 'question_agent — AI 自动出题' },
  { key: 'paper_generation',    label: '试卷生成',  desc: 'paper_agent — AI 智能组卷与试卷优化' },
  { key: 'paper_import',        label: '试卷导入解析', desc: 'paper_parse_agent — Word 导入智能解析' },
  { key: 'scoring',             label: 'AI 评分',   desc: 'scoring_agent — 主观题智能评分' },
  { key: 'interactive',         label: '交互对话',  desc: 'interactive_agent — 情景对话评测' },
  { key: 'annotation',          label: '内容标注',  desc: 'annotation_agent — 素材自动标注' },
  { key: 'review',              label: '题目审核',  desc: 'review_agent — AI 质量审核' },
  { key: 'indicator',           label: '指标分析',  desc: 'indicator_agents — 评测指标分析' },
]

// ── State ─────────────────────────────────────────────────────────────────────
const activeTab = ref('llm')

// Providers
const providers = ref<any[]>([])
const loadingProviders = ref(false)

const enabledProviders = computed(() => providers.value.filter(p => p.enabled))

// Assignments
const assignments = reactive<Record<string, string | null>>({
  question_generation: null, paper_generation: null, paper_import: null, scoring: null, interactive: null,
  annotation: null, review: null, indicator: null,
})
const loadingAssignments = ref(false)
const savingAssignments = ref(false)
const testingModule = ref<string | null>(null)
const assignmentResults = reactive<Record<string, any>>({})

// Modal
const modalVisible = ref(false)
const editingProvider = ref<any>(null)
const savingProvider = ref(false)
const testingInModal = ref(false)
const modalTestResult = ref<any>(null)
const fetchingModels = ref(false)
const fetchedModels = ref<string[]>([])

const form = reactive({
  provider_type: 'openai',
  name: '',
  api_key: '',
  base_url: 'https://api.openai.com/v1',
  model: '',
  enabled: true,
})

const presetModels = computed(() => TYPE_META[form.provider_type]?.models ?? [])
const modelPlaceholder = computed(() => TYPE_META[form.provider_type]?.placeholder ?? '模型名称')

// ── API calls ─────────────────────────────────────────────────────────────────
async function loadProviders() {
  loadingProviders.value = true
  try {
    const res: any = await request.get('/system/providers')
    providers.value = res
  } catch { message.error('加载提供方失败') }
  finally { loadingProviders.value = false }
}

async function loadAssignments() {
  loadingAssignments.value = true
  try {
    const res: any = await request.get('/system/assignments')
    Object.assign(assignments, res)
  } catch { message.error('加载分配失败') }
  finally { loadingAssignments.value = false }
}

async function saveAssignments() {
  savingAssignments.value = true
  try {
    await request.put('/system/assignments', { ...assignments })
    message.success('分配已保存')
  } catch { message.error('保存失败') }
  finally { savingAssignments.value = false }
}

async function deleteProvider(id: string) {
  try {
    await request.delete(`/system/providers/${id}`)
    providers.value = providers.value.filter(p => p.id !== id)
    // Clear assignments that used this provider
    for (const k of Object.keys(assignments)) {
      if (assignments[k] === id) assignments[k] = null
    }
    message.success('已删除')
  } catch { message.error('删除失败') }
}

async function testProvider(p: any) {
  try {
    message.loading({ content: `测试 ${p.name}...`, key: p.id })
    const res = await request.post('/system/providers/test', {
      api_key: p.api_key, base_url: p.base_url, model: p.model,
    })
    message.success({ content: `✓ ${p.name} 连接成功（${(res as any).model}）`, key: p.id, duration: 3 })
  } catch (err: any) {
    const detail = err.response?.data?.detail ?? '连接失败'
    message.error({ content: `✗ ${p.name}：${detail}`, key: p.id, duration: 4 })
  }
}

async function testAssignment(moduleKey: string) {
  const providerId = assignments[moduleKey]
  if (!providerId) return
  const p = providers.value.find(x => x.id === providerId)
  if (!p) return
  testingModule.value = moduleKey
  delete assignmentResults[moduleKey]
  try {
    const res = await request.post('/system/providers/test', {
      api_key: p.api_key, base_url: p.base_url, model: p.model,
    })
    assignmentResults[moduleKey] = { success: true, model: (res as any).model }
  } catch (err: any) {
    assignmentResults[moduleKey] = { success: false, error: err.response?.data?.detail ?? '失败' }
  } finally {
    testingModule.value = null
  }
}

async function fetchModels() {
  if (!form.base_url) { message.warning('请先填写服务地址'); return }
  fetchingModels.value = true
  try {
    const res = await request.post('/system/providers/models', {
      api_key: form.api_key, base_url: form.base_url,
    })
    fetchedModels.value = (res as any).models ?? []
    if (fetchedModels.value.length === 0) message.warning('未获取到模型列表')
    else message.success(`获取到 ${fetchedModels.value.length} 个模型`)
  } catch (err: any) {
    message.error(err.response?.data?.detail ?? '获取失败')
  } finally {
    fetchingModels.value = false
  }
}

async function testInModal() {
  testingInModal.value = true
  modalTestResult.value = null
  try {
    const res = await request.post('/system/providers/test', {
      api_key: form.api_key, base_url: form.base_url, model: form.model,
    })
    modalTestResult.value = { success: true, model: (res as any).model }
  } catch (err: any) {
    modalTestResult.value = { success: false, error: err.response?.data?.detail ?? '连接失败' }
  } finally {
    testingInModal.value = false }
}

async function submitProvider() {
  if (!form.name || !form.model) {
    message.warning('名称和模型为必填项')
    return
  }
  if (isLocalProvider.value && !form.base_url) {
    message.warning('本地服务需要填写服务地址')
    return
  }
  savingProvider.value = true
  try {
    if (editingProvider.value) {
      const res: any = await request.put(`/system/providers/${editingProvider.value.id}`, { ...form })
      const idx = providers.value.findIndex(p => p.id === editingProvider.value.id)
      if (idx >= 0) providers.value[idx] = res
    } else {
      const res: any = await request.post('/system/providers', { ...form })
      providers.value.push(res)
    }
    modalVisible.value = false
    message.success(editingProvider.value ? '更新成功' : '添加成功')
  } catch { message.error('保存失败') }
  finally { savingProvider.value = false }
}

// ── Modal helpers ─────────────────────────────────────────────────────────────
function openProviderModal(provider?: any) {
  editingProvider.value = provider ?? null
  modalTestResult.value = null
  fetchedModels.value = []
  if (provider) {
    Object.assign(form, { ...provider })
  } else {
    Object.assign(form, {
      provider_type: 'openai', name: '', api_key: '',
      base_url: TYPE_META.openai.base_url, model: '', enabled: true,
    })
  }
  modalVisible.value = true
}

function onTypeChange(type: string) {
  const meta = TYPE_META[type]
  if (meta) {
    form.base_url = meta.base_url
    if (!editingProvider.value) {
      form.name = meta.label
      form.model = ''
    }
  }
  modalTestResult.value = null
  fetchedModels.value = []
}

onMounted(() => {
  loadProviders()
  loadAssignments()
})
</script>

<style scoped>
.page-container { padding: 4px 0; }
.page-header h2 { margin: 0 0 4px; font-size: 22px; font-weight: 700; }
.sub-title { margin: 0 0 16px; color: var(--text-hint); font-size: 13px; }

.main-tabs { background: #fff; border-radius: 8px; padding: 0 16px; }

.section {
  margin-bottom: 32px;
  padding: 20px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
}

.section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
}
.section-title { font-size: 15px; font-weight: 600; margin-right: 12px; }
.section-hint  { font-size: 12px; color: var(--text-hint); }

/* Provider cards */
.provider-list { display: flex; flex-direction: column; gap: 10px; }
.provider-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  transition: box-shadow 0.2s;
}
.provider-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.provider-card.disabled { opacity: 0.5; }

.provider-left { display: flex; align-items: center; gap: 12px; flex: 1; overflow: hidden; }
.type-tag { flex-shrink: 0; }
.provider-name { font-weight: 600; font-size: 14px; flex-shrink: 0; }
.provider-meta  { font-size: 12px; color: var(--text-hint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 260px; }
.provider-model { font-size: 12px; color: #1677ff; font-family: monospace; flex-shrink: 0; }

.provider-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

/* Assignment table */
.assignment-table { display: flex; flex-direction: column; gap: 0; }
.assignment-row {
  display: flex;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid #f0f0f0;
  gap: 16px;
}
.assignment-row:last-child { border-bottom: none; }

.assignment-label { width: 200px; flex-shrink: 0; }
.mod-name { display: block; font-weight: 600; font-size: 14px; }
.mod-desc { display: block; font-size: 12px; color: var(--text-hint); }

.assignment-select { flex: 1; }
.assignment-test   { display: flex; align-items: center; flex-shrink: 0; }

/* Modal */
.field-hint { font-size: 12px; color: var(--text-hint); margin-top: 4px; }
.field-hint code { background: #f5f5f5; padding: 1px 4px; border-radius: 3px; }
.preset-models { margin-top: 6px; }
.model-tag { cursor: pointer; font-family: monospace; }
.model-tag:hover { opacity: 0.75; }
</style>
