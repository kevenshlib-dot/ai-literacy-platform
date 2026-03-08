<template>
  <div class="page-container">
    <div class="page-header">
      <h2>题库管理</h2>
      <a-space>
        <a-button @click="showBankBuildModal">
          <template #icon><ThunderboltOutlined /></template>
          新建题库
        </a-button>
        <a-button @click="showCreateModal">
          <template #icon><PlusOutlined /></template>
          新建题目
        </a-button>
        <a-button size="small" style="background: #1f4e79; color: #fff; border-color: #1f4e79" @click="showImportModal">
          <template #icon><DownloadOutlined /></template>
          导入题库
        </a-button>
      </a-space>
    </div>

    <!-- Tab Switcher -->
    <a-tabs v-model:activeKey="activeTab" @change="onTabChange" class="main-tabs">
      <a-tab-pane key="all" tab="全部题目" />
      <a-tab-pane key="review">
        <template #tab>
          <a-badge :count="reviewPendingTotal" :offset="[10, -2]" :overflow-count="999">
            <span><AuditOutlined style="margin-right: 4px" />批量审核</span>
          </a-badge>
        </template>
      </a-tab-pane>
    </a-tabs>

    <!-- ========== Tab: 全部题目 ========== -->
    <template v-if="activeTab === 'all'">
      <!-- Filter Bar -->
      <a-card class="filter-card" :bordered="false">
        <a-row :gutter="16">
          <a-col :span="5">
            <a-input
              v-model:value="filters.keyword"
              placeholder="搜索题干关键词"
              allow-clear
              @press-enter="fetchQuestions"
            >
              <template #prefix><SearchOutlined /></template>
            </a-input>
          </a-col>
          <a-col :span="4">
            <a-select v-model:value="filters.status" placeholder="状态" allow-clear style="width: 100%">
              <a-select-option value="draft">草稿</a-select-option>
              <a-select-option value="pending_review">待审核</a-select-option>
              <a-select-option value="approved">已通过</a-select-option>
              <a-select-option value="rejected">已拒绝</a-select-option>
              <a-select-option value="archived">已归档</a-select-option>
            </a-select>
          </a-col>
          <a-col :span="4">
            <a-select v-model:value="filters.question_type" placeholder="题型" allow-clear style="width: 100%">
              <a-select-option value="single_choice">单选题</a-select-option>
              <a-select-option value="multiple_choice">多选题</a-select-option>
              <a-select-option value="true_false">判断题</a-select-option>
              <a-select-option value="fill_blank">填空题</a-select-option>
              <a-select-option value="short_answer">简答题</a-select-option>
            </a-select>
          </a-col>
          <a-col :span="3">
            <a-select v-model:value="filters.difficulty" placeholder="难度" allow-clear style="width: 100%">
              <a-select-option :value="1">1 - 入门</a-select-option>
              <a-select-option :value="2">2 - 简单</a-select-option>
              <a-select-option :value="3">3 - 中等</a-select-option>
              <a-select-option :value="4">4 - 困难</a-select-option>
              <a-select-option :value="5">5 - 专家</a-select-option>
            </a-select>
          </a-col>
          <a-col :span="4">
            <a-select v-model:value="filters.dimension" placeholder="AI素养维度" allow-clear style="width: 100%">
              <a-select-option value="AI基础知识">AI基础知识</a-select-option>
              <a-select-option value="AI技术应用">AI技术应用</a-select-option>
              <a-select-option value="AI伦理安全">AI伦理安全</a-select-option>
              <a-select-option value="AI批判思维">AI批判思维</a-select-option>
              <a-select-option value="AI创新实践">AI创新实践</a-select-option>
            </a-select>
          </a-col>
          <a-col :span="4">
            <a-space>
              <a-button type="primary" @click="fetchQuestions">查询</a-button>
              <a-button @click="resetFilters">重置</a-button>
            </a-space>
          </a-col>
        </a-row>
      </a-card>

      <!-- Batch Actions -->
      <a-card v-if="selectedRowKeys.length > 0" :bordered="false" style="margin-bottom: 16px">
        <div style="display: flex; justify-content: space-between; align-items: center">
        <a-space>
          <span>已选 {{ selectedRowKeys.length }} 项</span>
          <a-button size="small" style="background: #1f4e79; color: #fff; border-color: #1f4e79" @click="batchApprove">批量通过</a-button>
          <a-button size="small" style="background: #1f4e79; color: #fff; border-color: #1f4e79" @click="batchReject">批量拒绝</a-button>
          <a-button size="small" style="background: #1f4e79; color: #fff; border-color: #1f4e79" @click="batchDelete">批量删除</a-button>
          <a-button size="small" style="background: #1f4e79; color: #fff; border-color: #1f4e79" @click="batchSubmit">批量提交审核</a-button>
        </a-space>
        <a-button size="small" style="background: #1f4e79; color: #fff; border-color: #1f4e79" @click="exportSelectedMd">
          <template #icon><UploadOutlined /></template>
          导出题库
        </a-button>
        </div>
      </a-card>

      <!-- Questions Table -->
      <a-card :bordered="false">
        <a-table
          :columns="columns"
          :data-source="questions"
          :loading="loading"
          :pagination="pagination"
          :row-selection="{ selectedRowKeys, onChange: onSelectChange }"
          row-key="id"
          @change="handleTableChange"
          size="middle"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'stem'">
              <a @click="showDetail(record)">{{ truncate(record.stem, 40) }}</a>
            </template>
            <template v-if="column.key === 'question_type'">
              <a-tag :color="typeColor(record.question_type)">{{ typeLabel(record.question_type) }}</a-tag>
            </template>
            <template v-if="column.key === 'difficulty'">
              <a-rate :value="record.difficulty" disabled :count="5" style="font-size: 12px" />
            </template>
            <template v-if="column.key === 'dimension'">
              <a-tag v-if="record.dimension" :color="dimensionColor(record.dimension)">{{ record.dimension }}</a-tag>
              <span v-else style="color: #ccc">未分类</span>
            </template>
            <template v-if="column.key === 'status'">
              <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
            </template>
            <template v-if="column.key === 'created_at'">
              {{ formatDate(record.created_at) }}
            </template>
            <template v-if="column.key === 'actions'">
              <a-space>
                <a-button size="small" type="link" @click="showDetail(record)">详情</a-button>
                <a-button
                  v-if="record.status === 'draft'"
                  size="small"
                  type="link"
                  @click="submitForReview(record.id)"
                >提交审核</a-button>
                <a-button
                  v-if="record.status === 'draft' || record.status === 'pending_review'"
                  size="small"
                  type="link"
                  style="color: #52c41a"
                  @click="quickApprove(record.id)"
                >通过</a-button>
                <a-button
                  v-if="record.status === 'draft'"
                  size="small"
                  type="link"
                  @click="editQuestion(record)"
                >编辑</a-button>
                <a-popconfirm
                  title="确认删除该题目？"
                  @confirm="deleteQuestion(record.id)"
                >
                  <a-button size="small" type="link" danger>删除</a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </template>
        </a-table>
      </a-card>
    </template>

    <!-- ========== Tab: 批量审核 ========== -->
    <template v-if="activeTab === 'review'">
      <!-- Review Stats Bar -->
      <a-card :bordered="false" class="filter-card">
        <a-row :gutter="16" align="middle">
          <a-col :flex="'auto'">
            <a-space :size="24">
              <a-statistic title="待审核题目" :value="reviewPendingTotal" :value-style="{ color: '#1f4e79', fontSize: '24px' }" />
              <a-divider type="vertical" style="height: 40px" />
              <a-space>
                <a-select v-model:value="reviewFilters.question_type" placeholder="筛选题型" allow-clear style="width: 140px" @change="fetchReviewQuestions">
                  <a-select-option value="single_choice">单选题</a-select-option>
                  <a-select-option value="multiple_choice">多选题</a-select-option>
                  <a-select-option value="true_false">判断题</a-select-option>
                  <a-select-option value="fill_blank">填空题</a-select-option>
                  <a-select-option value="short_answer">简答题</a-select-option>
                </a-select>
                <a-select v-model:value="reviewFilters.dimension" placeholder="筛选维度" allow-clear style="width: 140px" @change="fetchReviewQuestions">
                  <a-select-option value="AI基础知识">AI基础知识</a-select-option>
                  <a-select-option value="AI技术应用">AI技术应用</a-select-option>
                  <a-select-option value="AI伦理安全">AI伦理安全</a-select-option>
                  <a-select-option value="AI批判思维">AI批判思维</a-select-option>
                  <a-select-option value="AI创新实践">AI创新实践</a-select-option>
                </a-select>
              </a-space>
            </a-space>
          </a-col>
          <a-col>
            <a-space>
              <a-button @click="fetchReviewQuestions" :loading="reviewLoading">
                <template #icon><ReloadOutlined /></template>
                刷新
              </a-button>
              <a-button
                type="primary"
                :disabled="reviewSelectedKeys.length === 0"
                @click="reviewBatchApprove"
                style="background: #52c41a; border-color: #52c41a"
              >
                <template #icon><CheckCircleOutlined /></template>
                批量通过 {{ reviewSelectedKeys.length > 0 ? `(${reviewSelectedKeys.length})` : '' }}
              </a-button>
              <a-button
                danger
                :disabled="reviewSelectedKeys.length === 0"
                @click="reviewBatchReject"
              >
                <template #icon><CloseCircleOutlined /></template>
                批量拒绝 {{ reviewSelectedKeys.length > 0 ? `(${reviewSelectedKeys.length})` : '' }}
              </a-button>
            </a-space>
          </a-col>
        </a-row>
      </a-card>

      <!-- Review Table -->
      <a-card :bordered="false">
        <a-alert
          v-if="reviewQuestions.length === 0 && !reviewLoading"
          type="success"
          message="暂无待审核题目"
          description="所有题目均已审核完毕，可前往「全部题目」查看已通过的题目。"
          show-icon
          style="margin-bottom: 16px"
        />
        <a-table
          v-else
          :columns="reviewColumns"
          :data-source="filteredReviewQuestions"
          :loading="reviewLoading"
          :pagination="reviewPagination"
          :row-selection="{ selectedRowKeys: reviewSelectedKeys, onChange: onReviewSelectChange }"
          row-key="id"
          @change="handleReviewTableChange"
          size="middle"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'stem'">
              <a @click="showDetail(record)">{{ truncate(record.stem, 50) }}</a>
            </template>
            <template v-if="column.key === 'question_type'">
              <a-tag :color="typeColor(record.question_type)">{{ typeLabel(record.question_type) }}</a-tag>
            </template>
            <template v-if="column.key === 'difficulty'">
              <a-rate :value="record.difficulty" disabled :count="5" style="font-size: 12px" />
            </template>
            <template v-if="column.key === 'dimension'">
              <a-tag v-if="record.dimension" :color="dimensionColor(record.dimension)">{{ record.dimension }}</a-tag>
              <span v-else style="color: #ccc">未分类</span>
            </template>
            <template v-if="column.key === 'bloom_level'">
              <a-tag v-if="record.bloom_level" color="geekblue">{{ bloomLabel(record.bloom_level) }}</a-tag>
              <span v-else style="color: #ccc">-</span>
            </template>
            <template v-if="column.key === 'created_at'">
              {{ formatDate(record.created_at) }}
            </template>
            <template v-if="column.key === 'review_actions'">
              <a-space>
                <a-button size="small" type="link" @click="showDetail(record)">
                  <template #icon><EyeOutlined /></template>
                  查看
                </a-button>
                <a-button size="small" type="link" @click="runAICheck(record.id)" :loading="aiCheckLoading && detailQuestion?.id === record.id">
                  <template #icon><RobotOutlined /></template>
                  AI检查
                </a-button>
                <a-button size="small" type="link" style="color: #52c41a" @click="quickReviewApprove(record.id)">
                  <template #icon><CheckOutlined /></template>
                  通过
                </a-button>
                <a-button size="small" type="link" danger @click="reviewAction(record.id, 'reject')">
                  <template #icon><CloseOutlined /></template>
                  拒绝
                </a-button>
              </a-space>
            </template>
          </template>
        </a-table>
      </a-card>
    </template>

    <!-- Create/Edit Modal -->
    <a-modal
      v-model:open="createModalVisible"
      :title="editingQuestion ? '编辑题目' : '新建题目'"
      :width="720"
      @ok="handleCreateOrUpdate"
      :confirm-loading="submitLoading"
    >
      <a-form :label-col="{ span: 4 }" :wrapper-col="{ span: 20 }">
        <a-form-item label="题型" required>
          <a-select v-model:value="form.question_type" placeholder="选择题型">
            <a-select-option value="single_choice">单选题</a-select-option>
            <a-select-option value="multiple_choice">多选题</a-select-option>
            <a-select-option value="true_false">判断题</a-select-option>
            <a-select-option value="fill_blank">填空题</a-select-option>
            <a-select-option value="short_answer">简答题</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="题干" required>
          <a-textarea v-model:value="form.stem" :rows="3" placeholder="请输入题干" />
        </a-form-item>
        <a-form-item v-if="hasOptions" label="选项">
          <a-row :gutter="8" v-for="opt in ['A', 'B', 'C', 'D']" :key="opt" style="margin-bottom: 4px">
            <a-col :span="2"><strong>{{ opt }}.</strong></a-col>
            <a-col :span="22">
              <a-input v-model:value="form.options[opt]" :placeholder="`选项${opt}`" />
            </a-col>
          </a-row>
        </a-form-item>
        <a-form-item label="正确答案" required>
          <a-input v-model:value="form.correct_answer" placeholder="如: A 或 AB" />
        </a-form-item>
        <a-form-item label="解析">
          <a-textarea v-model:value="form.explanation" :rows="2" placeholder="答案解析" />
        </a-form-item>
        <a-form-item label="难度">
          <a-rate v-model:value="form.difficulty" :count="5" />
        </a-form-item>
        <a-form-item label="AI素养维度">
          <a-select v-model:value="form.dimension" placeholder="选择AI素养维度" allow-clear style="width: 100%">
            <a-select-option value="AI基础知识">AI基础知识</a-select-option>
            <a-select-option value="AI技术应用">AI技术应用</a-select-option>
            <a-select-option value="AI伦理安全">AI伦理安全</a-select-option>
            <a-select-option value="AI批判思维">AI批判思维</a-select-option>
            <a-select-option value="AI创新实践">AI创新实践</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="认知层次">
          <a-select v-model:value="form.bloom_level" placeholder="选择认知层次" allow-clear>
            <a-select-option value="remember">记忆</a-select-option>
            <a-select-option value="understand">理解</a-select-option>
            <a-select-option value="apply">应用</a-select-option>
            <a-select-option value="analyze">分析</a-select-option>
            <a-select-option value="evaluate">评价</a-select-option>
            <a-select-option value="create">创造</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- Detail Drawer -->
    <a-drawer
      v-model:open="detailVisible"
      title="题目详情"
      :width="640"
    >
      <template v-if="detailQuestion">
        <a-descriptions :column="1" bordered size="small">
          <a-descriptions-item label="题型">
            <a-tag :color="typeColor(detailQuestion.question_type)">
              {{ typeLabel(detailQuestion.question_type) }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="题干">{{ detailQuestion.stem }}</a-descriptions-item>
          <a-descriptions-item v-if="detailQuestion.options" label="选项">
            <div v-for="(val, key) in detailQuestion.options" :key="key">
              <strong>{{ key }}.</strong> {{ val }}
              <CheckOutlined v-if="detailQuestion.correct_answer.includes(String(key))" style="color: #52c41a; margin-left: 4px" />
            </div>
          </a-descriptions-item>
          <a-descriptions-item label="正确答案">
            <a-tag color="green">{{ detailQuestion.correct_answer }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item v-if="detailQuestion.explanation" label="解析">
            {{ detailQuestion.explanation }}
          </a-descriptions-item>
          <a-descriptions-item label="难度">
            <a-rate :value="detailQuestion.difficulty" disabled :count="5" style="font-size: 12px" />
          </a-descriptions-item>
          <a-descriptions-item label="状态">
            <a-tag :color="statusColor(detailQuestion.status)">{{ statusLabel(detailQuestion.status) }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item v-if="detailQuestion.dimension" label="维度">{{ detailQuestion.dimension }}</a-descriptions-item>
          <a-descriptions-item v-if="detailQuestion.bloom_level" label="认知层次">{{ bloomLabel(detailQuestion.bloom_level) }}</a-descriptions-item>
          <a-descriptions-item v-if="detailQuestion.review_comment" label="审核意见">{{ detailQuestion.review_comment }}</a-descriptions-item>
          <a-descriptions-item label="创建时间">{{ formatDate(detailQuestion.created_at) }}</a-descriptions-item>
        </a-descriptions>

        <!-- Review Actions -->
        <div style="margin-top: 16px">
          <a-space>
            <a-button @click="runAICheck(detailQuestion.id)" :loading="aiCheckLoading">
              <template #icon><RobotOutlined /></template>
              AI质量检查
            </a-button>
            <a-button
              v-if="detailQuestion.status === 'pending_review'"
              type="primary"
              @click="reviewAction(detailQuestion.id, 'approve')"
            >通过</a-button>
            <a-button
              v-if="detailQuestion.status === 'pending_review'"
              danger
              @click="reviewAction(detailQuestion.id, 'reject')"
            >拒绝</a-button>
          </a-space>
        </div>

        <!-- AI Check Result -->
        <a-card v-if="aiCheckResult" title="AI质量评估" size="small" style="margin-top: 16px">
          <a-descriptions :column="2" size="small">
            <a-descriptions-item label="总分">
              <a-tag :color="aiCheckResult.overall_score >= 3.5 ? 'green' : aiCheckResult.overall_score >= 2.5 ? 'orange' : 'red'">
                {{ aiCheckResult.overall_score }}
              </a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="建议">{{ aiCheckResult.recommendation === 'approve' ? '通过' : aiCheckResult.recommendation === 'revise' ? '修改' : '拒绝' }}</a-descriptions-item>
          </a-descriptions>
          <div v-if="aiCheckResult.scores" style="margin-top: 8px">
            <a-tag v-for="(score, key) in aiCheckResult.scores" :key="key" style="margin-bottom: 4px">
              {{ scoreLabel(key as string) }}: {{ score }}
            </a-tag>
          </div>
          <p v-if="aiCheckResult.comments" style="margin-top: 8px; color: #666">{{ aiCheckResult.comments }}</p>
        </a-card>

        <!-- Review History -->
        <a-card title="审核记录" size="small" style="margin-top: 16px" v-if="reviewHistory.length > 0">
          <a-timeline>
            <a-timeline-item
              v-for="record in reviewHistory"
              :key="record.id"
              :color="record.action === 'approve' ? 'green' : record.action === 'reject' ? 'red' : 'blue'"
            >
              <span>{{ actionLabel(record.action) }}</span>
              <span v-if="record.comment"> - {{ record.comment }}</span>
              <br />
              <small style="color: #999">{{ formatDate(record.created_at) }}</small>
            </a-timeline-item>
          </a-timeline>
        </a-card>
      </template>
    </a-drawer>

    <!-- Review Comment Modal -->
    <a-modal
      v-model:open="reviewModalVisible"
      :title="reviewModalAction === 'approve' ? '通过审核' : '拒绝题目'"
      @ok="confirmReview"
    >
      <a-form-item label="审核意见">
        <a-textarea v-model:value="reviewComment" :rows="3" placeholder="请输入审核意见（可选）" />
      </a-form-item>
    </a-modal>

    <!-- Question Bank Build Modal -->
    <a-modal
      v-model:open="bankBuildModal.visible"
      title="题库建设 - 从素材生成题目"
      width="720px"
      @ok="handleBankBuild"
      :confirm-loading="bankBuildModal.loading"
      :ok-text="bankBuildModal.loading ? '生成中...' : '开始生成'"
    >
      <a-form layout="vertical">
        <a-form-item label="选择素材（可多选，不选则直接用AI出题）">
          <a-select
            v-model:value="bankBuildModal.materialIds"
            placeholder="可选，不选则直接用AI知识出题"
            mode="multiple"
            show-search
            :filter-option="filterMaterialOption"
            :loading="bankBuildModal.materialsLoading"
            @change="onMaterialChange"
            style="width: 100%"
            allow-clear
          >
            <a-select-option v-for="m in parsedMaterials" :key="m.id" :value="m.id">
              {{ m.title }} ({{ m.format }})
            </a-select-option>
          </a-select>
        </a-form-item>

        <a-alert
          v-if="bankBuildModal.materialInfo"
          type="info"
          :message="bankBuildModal.materialInfo"
          style="margin-bottom: 16px"
        />

        <a-form-item label="出题提示词（可选）">
          <a-textarea
            v-model:value="bankBuildModal.customPrompt"
            placeholder="可输入对出题的特殊要求，如：侧重考察应用能力、避免过于简单的记忆题、题目需贴近实际工作场景..."
            :maxlength="500"
            show-count
            :rows="3"
          />
        </a-form-item>

        <a-button
          type="dashed"
          block
          @click="autoSuggest"
          :loading="bankBuildModal.suggestLoading"
          style="margin-bottom: 16px"
        >
          <template #icon><ThunderboltOutlined /></template>
          一键自动生成（AI推荐最佳配比）
        </a-button>

        <a-form-item label="题型分配">
          <a-row :gutter="[8, 8]">
            <a-col :span="8">
              <a-input-number v-model:value="bankTypeDist.single_choice" :min="0" :max="30" addon-before="单选题" style="width: 100%" />
            </a-col>
            <a-col :span="8">
              <a-input-number v-model:value="bankTypeDist.multiple_choice" :min="0" :max="30" addon-before="多选题" style="width: 100%" />
            </a-col>
            <a-col :span="8">
              <a-input-number v-model:value="bankTypeDist.true_false" :min="0" :max="30" addon-before="判断题" style="width: 100%" />
            </a-col>
            <a-col :span="8">
              <a-input-number v-model:value="bankTypeDist.fill_blank" :min="0" :max="30" addon-before="填空题" style="width: 100%" />
            </a-col>
            <a-col :span="8">
              <a-input-number v-model:value="bankTypeDist.short_answer" :min="0" :max="30" addon-before="简答题" style="width: 100%" />
            </a-col>
            <a-col :span="8">
              <div style="line-height: 32px; text-align: center; font-weight: 600; color: #1F4E79">
                合计: {{ bankTotalCount }} 题
              </div>
            </a-col>
          </a-row>
        </a-form-item>

        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="难度等级">
              <a-slider v-model:value="bankBuildModal.difficulty" :min="1" :max="5" :marks="{1:'入门',3:'中等',5:'专家'}" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="认知层次（可选）">
              <a-select v-model:value="bankBuildModal.bloomLevel" placeholder="不限" allow-clear style="width: 100%">
                <a-select-option value="remember">记忆</a-select-option>
                <a-select-option value="understand">理解</a-select-option>
                <a-select-option value="apply">应用</a-select-option>
                <a-select-option value="analyze">分析</a-select-option>
                <a-select-option value="evaluate">评价</a-select-option>
                <a-select-option value="create">创造</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>

      <div v-if="bankBuildModal.loading" style="margin-top: 12px">
        <div style="display: flex; justify-content: space-between; margin-bottom: 4px">
          <span style="color: #1F4E79; font-weight: 500">{{ genProgress.statusText }}</span>
          <span style="color: #999">{{ genProgress.percent }}%</span>
        </div>
        <a-progress
          :percent="genProgress.percent"
          :status="genProgress.percent >= 100 ? 'success' : 'active'"
          :stroke-color="{ from: '#1F4E79', to: '#52c41a' }"
        />
        <div style="color: #999; font-size: 12px; margin-top: 4px">
          已用时 {{ genProgress.elapsed }}，预计还需 {{ genProgress.remaining }}
        </div>
      </div>
    </a-modal>

    <!-- Generation Result Modal -->
    <a-modal
      v-model:open="bankResultModal.visible"
      title="题目生成完成"
      :footer="null"
      width="480px"
    >
      <a-result
        status="success"
        :title="`成功生成 ${bankResultModal.generated} 道题目`"
        sub-title="所有题目已保存为草稿状态，可在列表中查看和审核"
      >
        <template #extra>
          <a-button type="primary" @click="bankResultModal.visible = false; fetchQuestions()">
            查看题目列表
          </a-button>
        </template>
      </a-result>
    </a-modal>

    <!-- Import MD Modal -->
    <a-modal
      v-model:open="importModalVisible"
      title="导入题目（Markdown 格式）"
      :footer="null"
      width="520px"
    >
      <a-alert
        type="info"
        show-icon
        style="margin-bottom: 16px"
        message="请上传通过本系统导出的 .md 格式题库文件，导入的题目将以草稿状态进入审核流程。"
      />

      <a-upload-dragger
        :before-upload="handleImportUpload"
        :show-upload-list="false"
        accept=".md"
        :disabled="importLoading"
      >
        <p class="ant-upload-drag-icon">
          <UploadOutlined />
        </p>
        <p class="ant-upload-text">点击或拖拽 .md 文件到此区域</p>
        <p class="ant-upload-hint">仅支持 Markdown 格式的题库文件</p>
      </a-upload-dragger>

      <div v-if="importLoading" style="margin-top: 16px; text-align: center">
        <a-spin tip="正在导入..." />
      </div>

      <a-result
        v-if="importResult"
        :status="importResult.failed > 0 ? 'warning' : 'success'"
        :title="`导入完成：成功 ${importResult.imported} 题${importResult.failed > 0 ? '，失败 ' + importResult.failed + ' 题' : ''}`"
        style="margin-top: 16px; padding: 16px 0"
      >
        <template #extra>
          <a-button type="primary" @click="importModalVisible = false; importResult = null; fetchQuestions()">
            查看题目列表
          </a-button>
        </template>
        <div v-if="importResult.errors && importResult.errors.length > 0">
          <a-alert type="error" style="text-align: left; margin-top: 8px">
            <template #message>
              <div v-for="(err, i) in importResult.errors" :key="i" style="font-size: 12px">{{ err }}</div>
            </template>
          </a-alert>
        </div>
      </a-result>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import {
  PlusOutlined,
  SearchOutlined,
  CheckOutlined,
  CheckCircleOutlined,
  CloseOutlined,
  CloseCircleOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  DownloadOutlined,
  UploadOutlined,
  AuditOutlined,
  ReloadOutlined,
  EyeOutlined,
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import request from '@/utils/request'

// ---- State ----
const loading = ref(false)
const submitLoading = ref(false)
const aiCheckLoading = ref(false)
const questions = ref<any[]>([])
const selectedRowKeys = ref<string[]>([])
const createModalVisible = ref(false)
const detailVisible = ref(false)
const reviewModalVisible = ref(false)
const editingQuestion = ref<any>(null)
const detailQuestion = ref<any>(null)
const aiCheckResult = ref<any>(null)
const reviewHistory = ref<any[]>([])
const reviewModalAction = ref('')
const reviewModalQuestionId = ref('')
const reviewComment = ref('')

// ---- Tab & Review State ----
const activeTab = ref('all')
const reviewLoading = ref(false)
const reviewQuestions = ref<any[]>([])
const reviewSelectedKeys = ref<string[]>([])
const reviewPendingTotal = ref(0)

const reviewFilters = reactive({
  question_type: undefined as string | undefined,
  dimension: undefined as string | undefined,
})

const reviewPagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条待审核`,
})

const filters = reactive({
  keyword: '',
  status: undefined as string | undefined,
  question_type: undefined as string | undefined,
  difficulty: undefined as number | undefined,
  dimension: '',
})

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条`,
})

const form = reactive({
  question_type: 'single_choice',
  stem: '',
  options: { A: '', B: '', C: '', D: '' } as Record<string, string>,
  correct_answer: '',
  explanation: '',
  difficulty: 3,
  dimension: '',
  bloom_level: undefined as string | undefined,
})

// ---- Computed ----
const hasOptions = computed(() =>
  ['single_choice', 'multiple_choice', 'true_false'].includes(form.question_type)
)

// ---- Table Columns ----
const columns = [
  { title: '题干', key: 'stem', dataIndex: 'stem', ellipsis: true, width: 280 },
  { title: '题型', key: 'question_type', dataIndex: 'question_type', width: 90 },
  { title: '难度', key: 'difficulty', dataIndex: 'difficulty', width: 140 },
  { title: '维度', key: 'dimension', dataIndex: 'dimension', width: 120, ellipsis: true },
  { title: '状态', key: 'status', dataIndex: 'status', width: 90 },
  { title: '创建时间', key: 'created_at', dataIndex: 'created_at', width: 120 },
  { title: '操作', key: 'actions', width: 200, fixed: 'right' as const },
]

// ---- Review Tab Columns ----
const reviewColumns = [
  { title: '题干', key: 'stem', dataIndex: 'stem', ellipsis: true, width: 300 },
  { title: '题型', key: 'question_type', dataIndex: 'question_type', width: 90 },
  { title: '难度', key: 'difficulty', dataIndex: 'difficulty', width: 140 },
  { title: '维度', key: 'dimension', dataIndex: 'dimension', width: 120, ellipsis: true },
  { title: '认知层次', key: 'bloom_level', dataIndex: 'bloom_level', width: 90 },
  { title: '创建时间', key: 'created_at', dataIndex: 'created_at', width: 110 },
  { title: '操作', key: 'review_actions', width: 260, fixed: 'right' as const },
]

// Computed: client-side filter for review tab (type & dimension)
const filteredReviewQuestions = computed(() => {
  let list = reviewQuestions.value
  if (reviewFilters.question_type) {
    list = list.filter(q => q.question_type === reviewFilters.question_type)
  }
  if (reviewFilters.dimension) {
    list = list.filter(q => q.dimension === reviewFilters.dimension)
  }
  return list
})

// ---- Label Maps ----
const typeMap: Record<string, string> = {
  single_choice: '单选题', multiple_choice: '多选题', true_false: '判断题',
  fill_blank: '填空题', short_answer: '简答题', essay: '论述题', sjt: '情境判断',
}
const statusMap: Record<string, string> = {
  draft: '草稿', pending_review: '待审核', approved: '已通过',
  rejected: '已拒绝', archived: '已归档',
}
const bloomMap: Record<string, string> = {
  remember: '记忆', understand: '理解', apply: '应用',
  analyze: '分析', evaluate: '评价', create: '创造',
}
const scoreMap: Record<string, string> = {
  stem_clarity: '题干清晰度', option_quality: '选项质量',
  answer_correctness: '答案正确性', knowledge_alignment: '知识对齐',
  difficulty_calibration: '难度校准',
}

function typeLabel(t: string) { return typeMap[t] || t }
function statusLabel(s: string) { return statusMap[s] || s }
function bloomLabel(b: string) { return bloomMap[b] || b }
function scoreLabel(k: string) { return scoreMap[k] || k }
function actionLabel(a: string) {
  return a === 'approve' ? '通过' : a === 'reject' ? '拒绝' : a === 'ai_check' ? 'AI检查' : a
}
function typeColor(t: string) {
  const map: Record<string, string> = {
    single_choice: 'blue', multiple_choice: 'purple', true_false: 'cyan',
    fill_blank: 'orange', short_answer: 'green', essay: 'magenta', sjt: 'gold',
  }
  return map[t] || 'default'
}
function dimensionColor(d: string) {
  const map: Record<string, string> = {
    'AI基础知识': 'blue', 'AI技术应用': 'green', 'AI伦理安全': 'orange',
    'AI批判思维': 'purple', 'AI创新实践': 'cyan',
  }
  return map[d] || 'default'
}
function statusColor(s: string) {
  const map: Record<string, string> = {
    draft: 'default', pending_review: 'processing', approved: 'success',
    rejected: 'error', archived: 'warning',
  }
  return map[s] || 'default'
}
function truncate(s: string, n: number) { return s.length > n ? s.slice(0, n) + '...' : s }
function formatDate(d: string) {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('zh-CN')
}

// ---- API Calls ----
async function fetchQuestions() {
  loading.value = true
  try {
    const params: any = {
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize,
    }
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.status) params.status = filters.status
    if (filters.question_type) params.question_type = filters.question_type
    if (filters.difficulty) params.difficulty = filters.difficulty
    if (filters.dimension) params.dimension = filters.dimension

    const data: any = await request.get('/questions', { params })
    questions.value = data.items || []
    pagination.total = data.total || 0
  } catch (e) {
    message.error('加载题目列表失败')
  } finally {
    loading.value = false
  }
}

function handleTableChange(pag: any) {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  fetchQuestions()
}

function onSelectChange(keys: string[]) {
  selectedRowKeys.value = keys
}

function resetFilters() {
  filters.keyword = ''
  filters.status = undefined
  filters.question_type = undefined
  filters.difficulty = undefined
  filters.dimension = ''
  pagination.current = 1
  fetchQuestions()
}

function resetForm() {
  form.question_type = 'single_choice'
  form.stem = ''
  form.options = { A: '', B: '', C: '', D: '' }
  form.correct_answer = ''
  form.explanation = ''
  form.difficulty = 3
  form.dimension = ''
  form.bloom_level = undefined
}

function showCreateModal() {
  editingQuestion.value = null
  resetForm()
  createModalVisible.value = true
}

function editQuestion(q: any) {
  editingQuestion.value = q
  form.question_type = q.question_type
  form.stem = q.stem
  form.options = q.options ? { ...q.options } : { A: '', B: '', C: '', D: '' }
  form.correct_answer = q.correct_answer
  form.explanation = q.explanation || ''
  form.difficulty = q.difficulty
  form.dimension = q.dimension || ''
  form.bloom_level = q.bloom_level || undefined
  createModalVisible.value = true
}

async function handleCreateOrUpdate() {
  if (!form.stem || !form.correct_answer) {
    message.warning('请填写题干和正确答案')
    return
  }
  submitLoading.value = true
  try {
    const payload: any = {
      question_type: form.question_type,
      stem: form.stem,
      correct_answer: form.correct_answer,
      explanation: form.explanation || undefined,
      difficulty: form.difficulty,
      dimension: form.dimension || undefined,
      bloom_level: form.bloom_level || undefined,
    }
    if (hasOptions.value) {
      payload.options = { ...form.options }
    }

    if (editingQuestion.value) {
      await request.put(`/questions/${editingQuestion.value.id}`, payload)
      message.success('题目更新成功')
    } else {
      await request.post('/questions', payload)
      message.success('题目创建成功')
    }
    createModalVisible.value = false
    fetchQuestions()
  } catch (e) {
    message.error('操作失败')
  } finally {
    submitLoading.value = false
  }
}

async function deleteQuestion(id: string) {
  try {
    await request.delete(`/questions/${id}`)
    message.success('题目已删除')
    fetchQuestions()
  } catch (e) {
    message.error('删除失败')
  }
}

async function submitForReview(id: string) {
  try {
    await request.post(`/questions/${id}/submit`)
    message.success('已提交审核')
    fetchQuestions()
    if (detailQuestion.value?.id === id) {
      detailQuestion.value.status = 'pending_review'
    }
  } catch (e) {
    message.error('提交失败')
  }
}

function reviewAction(id: string, action: string) {
  reviewModalQuestionId.value = id
  reviewModalAction.value = action
  reviewComment.value = ''
  reviewModalVisible.value = true
}

async function confirmReview() {
  try {
    // Handle batch reject from review tab
    if (reviewModalQuestionId.value === '__batch_review__') {
      await request.post('/questions/batch/review', {
        question_ids: reviewSelectedKeys.value,
        action: 'reject',
        comment: reviewComment.value || '批量拒绝',
      })
      message.success(`已批量拒绝 ${reviewSelectedKeys.value.length} 道题目`)
      reviewSelectedKeys.value = []
      reviewModalVisible.value = false
      await fetchReviewQuestions()
      return
    }

    const resp: any = await request.post(`/questions/${reviewModalQuestionId.value}/review`, {
      action: reviewModalAction.value,
      comment: reviewComment.value || undefined,
    })
    message.success(reviewModalAction.value === 'approve' ? '审核通过' : '已拒绝')
    reviewModalVisible.value = false

    // Refresh the appropriate tab
    if (activeTab.value === 'review') {
      await fetchReviewQuestions()
    } else {
      fetchQuestions()
    }

    if (detailQuestion.value?.id === reviewModalQuestionId.value) {
      detailQuestion.value.status = resp.status
      detailQuestion.value.review_comment = resp.review_comment
      loadReviewHistory(reviewModalQuestionId.value)
    }
  } catch (e) {
    message.error('审核操作失败')
  }
}

async function quickApprove(id: string) {
  try {
    await request.post(`/questions/${id}/review`, { action: 'approve' })
    message.success('已通过')
    fetchQuestions()
  } catch (e) {
    message.error('操作失败')
  }
}

async function showDetail(q: any) {
  detailQuestion.value = q
  aiCheckResult.value = null
  detailVisible.value = true
  await loadReviewHistory(q.id)
}

async function loadReviewHistory(qid: string) {
  try {
    reviewHistory.value = await request.get(`/questions/${qid}/review-history`) as any
  } catch {
    reviewHistory.value = []
  }
}

async function runAICheck(id: string) {
  aiCheckLoading.value = true
  try {
    aiCheckResult.value = await request.post(`/questions/${id}/ai-check`)
    message.success('AI质量检查完成')
    await loadReviewHistory(id)
  } catch (e) {
    message.error('AI检查失败')
  } finally {
    aiCheckLoading.value = false
  }
}

// ---- Review Tab Functions ----
async function fetchReviewQuestions() {
  reviewLoading.value = true
  try {
    const params: any = {
      skip: (reviewPagination.current - 1) * reviewPagination.pageSize,
      limit: reviewPagination.pageSize,
    }
    const data: any = await request.get('/questions/review/pending', { params })
    reviewQuestions.value = data.items || []
    reviewPagination.total = data.total || 0
    reviewPendingTotal.value = data.total || 0
  } catch (e) {
    message.error('加载待审核题目失败')
  } finally {
    reviewLoading.value = false
  }
}

async function fetchReviewCount() {
  try {
    const data: any = await request.get('/questions/review/pending', { params: { skip: 0, limit: 1 } })
    reviewPendingTotal.value = data.total || 0
  } catch {
    // silent fail
  }
}

function onTabChange(key: string) {
  if (key === 'review') {
    reviewSelectedKeys.value = []
    reviewPagination.current = 1
    fetchReviewQuestions()
  } else {
    fetchQuestions()
  }
}

function onReviewSelectChange(keys: string[]) {
  reviewSelectedKeys.value = keys
}

function handleReviewTableChange(pag: any) {
  reviewPagination.current = pag.current
  reviewPagination.pageSize = pag.pageSize
  fetchReviewQuestions()
}

async function quickReviewApprove(id: string) {
  try {
    await request.post(`/questions/${id}/review`, { action: 'approve' })
    message.success('已通过')
    // Remove from local list for immediate feedback
    reviewQuestions.value = reviewQuestions.value.filter(q => q.id !== id)
    reviewPendingTotal.value = Math.max(0, reviewPendingTotal.value - 1)
    reviewPagination.total = Math.max(0, reviewPagination.total - 1)
    // If list becomes empty and there are more pages, fetch next page
    if (reviewQuestions.value.length === 0 && reviewPagination.total > 0) {
      if (reviewPagination.current > 1) reviewPagination.current -= 1
      fetchReviewQuestions()
    }
  } catch (e) {
    message.error('操作失败')
  }
}

async function reviewBatchApprove() {
  if (reviewSelectedKeys.value.length === 0) return
  try {
    await request.post('/questions/batch/review', {
      question_ids: reviewSelectedKeys.value,
      action: 'approve',
    })
    message.success(`已批量通过 ${reviewSelectedKeys.value.length} 道题目`)
    reviewSelectedKeys.value = []
    await fetchReviewQuestions()
  } catch (e) {
    message.error('批量通过失败')
  }
}

async function reviewBatchReject() {
  if (reviewSelectedKeys.value.length === 0) return
  reviewModalAction.value = 'reject'
  reviewModalQuestionId.value = '__batch_review__'
  reviewComment.value = ''
  reviewModalVisible.value = true
}

// ---- Batch Operations ----

/**
 * After a batch operation, reload data and auto-advance to the next page
 * if the current page becomes empty (all items were operated on).
 */
async function reloadAfterBatch(operatedCount: number) {
  selectedRowKeys.value = []
  // If all items on this page were operated on, try to advance
  const currentPageSize = questions.value.length
  if (operatedCount >= currentPageSize && pagination.current > 0) {
    // Refresh total first to check if there are more pages
    const params: any = {
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize,
    }
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.status) params.status = filters.status
    if (filters.question_type) params.question_type = filters.question_type
    if (filters.difficulty) params.difficulty = filters.difficulty
    if (filters.dimension) params.dimension = filters.dimension

    const data: any = await request.get('/questions', { params })
    const remaining = data.items?.length || 0

    if (remaining === 0 && pagination.current > 1) {
      // Current page is empty, go back one page
      pagination.current -= 1
    }
    // else: stay on current page (items shifted in from next pages, or it's page 1)
  }
  await fetchQuestions()
}

async function batchSubmit() {
  try {
    const total = selectedRowKeys.value.length
    const data: any = await request.post('/questions/batch/submit', { question_ids: selectedRowKeys.value })
    const submitted = data.total || 0
    if (submitted === total) {
      message.success(`已提交 ${submitted} 道题目`)
    } else if (submitted > 0) {
      message.success(`已提交 ${submitted} 道题目，${total - submitted} 道非草稿状态已跳过`)
    } else {
      message.warning('所选题目均非草稿状态，无法提交')
    }
    await reloadAfterBatch(submitted)
  } catch (e) {
    message.error('批量提交失败')
  }
}

async function batchApprove() {
  try {
    await request.post('/questions/batch/review', {
      question_ids: selectedRowKeys.value,
      action: 'approve',
    })
    message.success('批量通过成功')
    await reloadAfterBatch(selectedRowKeys.value.length)
  } catch (e) {
    message.error('批量通过失败')
  }
}

async function batchReject() {
  try {
    await request.post('/questions/batch/review', {
      question_ids: selectedRowKeys.value,
      action: 'reject',
      comment: '批量拒绝',
    })
    message.success('批量拒绝成功')
    await reloadAfterBatch(selectedRowKeys.value.length)
  } catch (e) {
    message.error('批量拒绝失败')
  }
}

function batchDelete() {
  const count = selectedRowKeys.value.length
  Modal.confirm({
    title: '确认批量删除',
    content: `确定要删除选中的 ${count} 道题目吗？此操作不可恢复。`,
    okText: '确认删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        const data: any = await request.post('/questions/batch/delete', {
          question_ids: selectedRowKeys.value,
        })
        message.success(`已删除 ${data.deleted} 道题目`)
        await reloadAfterBatch(data.deleted || 0)
      } catch (e) {
        message.error('批量删除失败')
      }
    },
  })
}

// ---- Import / Export ----
const importModalVisible = ref(false)
const importLoading = ref(false)
const importResult = ref<any>(null)

function showImportModal() {
  importResult.value = null
  importModalVisible.value = true
}

async function handleImportUpload(file: File) {
  importLoading.value = true
  importResult.value = null
  try {
    const formData = new FormData()
    formData.append('file', file)
    const data: any = await request.post('/questions/batch/import-md', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    importResult.value = data
    if (data.imported > 0) {
      message.success(`成功导入 ${data.imported} 道题目`)
    }
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '导入失败')
  } finally {
    importLoading.value = false
  }
  return false // prevent default upload behaviour
}

async function exportSelectedMd() {
  if (selectedRowKeys.value.length === 0) {
    message.warning('请先选择要导出的题目')
    return
  }
  try {
    const resp = await request.post('/questions/batch/export-md', {
      question_ids: selectedRowKeys.value,
    }, {
      responseType: 'blob',
    })
    // Trigger file download
    const blob = new Blob([resp as any], { type: 'text/markdown; charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    const now = new Date()
    const ts = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`
    a.href = url
    a.download = `题库导出_${ts}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    message.success(`已导出 ${selectedRowKeys.value.length} 道题目`)
  } catch (e) {
    message.error('导出失败')
  }
}

// ---- Question Bank Build ----
const bankBuildModal = reactive({
  visible: false,
  loading: false,
  suggestLoading: false,
  materialsLoading: false,
  materialIds: [] as string[],
  materialInfo: null as string | null,
  difficulty: 3,
  bloomLevel: undefined as string | undefined,
  customPrompt: '',
})

const bankTypeDist = reactive({
  single_choice: 5,
  multiple_choice: 2,
  true_false: 3,
  fill_blank: 0,
  short_answer: 0,
})

const bankResultModal = reactive({
  visible: false,
  generated: 0,
})

// ---- Generation Progress ----
const genProgress = reactive({
  percent: 0,
  elapsed: '0秒',
  remaining: '估算中...',
  statusText: '准备中...',
})
let genTimer: ReturnType<typeof setInterval> | null = null
let genStartTime = 0

const GEN_PHASES = [
  { upTo: 15, text: '正在分析素材内容...' },
  { upTo: 35, text: '正在构建题目框架...' },
  { upTo: 55, text: '正在生成题干与选项...' },
  { upTo: 75, text: '正在生成答案解析...' },
  { upTo: 90, text: '正在校验题目质量...' },
  { upTo: 95, text: '即将完成...' },
]

function formatDuration(ms: number): string {
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}秒`
  const m = Math.floor(s / 60)
  return `${m}分${s % 60}秒`
}

function startGenProgress(totalQuestions: number) {
  genProgress.percent = 0
  genProgress.elapsed = '0秒'
  genProgress.remaining = '估算中...'
  genProgress.statusText = '准备中...'
  genStartTime = Date.now()

  // Estimate: ~8s per question, minimum 30s
  const estimatedMs = Math.max(totalQuestions * 8000, 30000)

  genTimer = setInterval(() => {
    const elapsed = Date.now() - genStartTime
    genProgress.elapsed = formatDuration(elapsed)

    // Asymptotic curve: fast at start, slows near 95%
    // percent = 95 * (1 - e^(-2.5 * t/T))
    const ratio = elapsed / estimatedMs
    const raw = 95 * (1 - Math.exp(-2.5 * ratio))
    genProgress.percent = Math.min(Math.round(raw), 95)

    // Update phase text
    for (const phase of GEN_PHASES) {
      if (genProgress.percent <= phase.upTo) {
        genProgress.statusText = phase.text
        break
      }
    }

    // Estimate remaining
    if (genProgress.percent > 5) {
      const speed = elapsed / genProgress.percent  // ms per percent
      const remainMs = (95 - genProgress.percent) * speed
      genProgress.remaining = formatDuration(remainMs)
    }
  }, 500)
}

function stopGenProgress(success: boolean) {
  if (genTimer) {
    clearInterval(genTimer)
    genTimer = null
  }
  if (success) {
    genProgress.percent = 100
    genProgress.statusText = '生成完成！'
    genProgress.remaining = '0秒'
    genProgress.elapsed = formatDuration(Date.now() - genStartTime)
  }
}

const parsedMaterials = ref<any[]>([])

const bankTotalCount = computed(() => {
  return Object.values(bankTypeDist).reduce((sum, v) => sum + (v || 0), 0)
})

function filterMaterialOption(input: string, option: any) {
  return (option?.children?.[0]?.children || '').toLowerCase().includes(input.toLowerCase())
}

async function showBankBuildModal() {
  bankBuildModal.materialIds = []
  bankBuildModal.materialInfo = null
  bankBuildModal.difficulty = 3
  bankBuildModal.bloomLevel = undefined
  bankBuildModal.customPrompt = ''
  bankTypeDist.single_choice = 5
  bankTypeDist.multiple_choice = 2
  bankTypeDist.true_false = 3
  bankTypeDist.fill_blank = 0
  bankTypeDist.short_answer = 0
  bankBuildModal.visible = true

  // Fetch parsed + vectorized materials
  bankBuildModal.materialsLoading = true
  try {
    const [d1, d2]: any[] = await Promise.all([
      request.get('/materials', { params: { status: 'parsed', skip: 0, limit: 100 } }),
      request.get('/materials', { params: { status: 'vectorized', skip: 0, limit: 100 } }),
    ])
    parsedMaterials.value = [...(d1.data || []), ...(d2.data || [])]
  } catch {
    parsedMaterials.value = []
  } finally {
    bankBuildModal.materialsLoading = false
  }
}

async function onMaterialChange(ids: string[]) {
  if (!ids || ids.length === 0) {
    bankBuildModal.materialInfo = null
    return
  }
  const names = ids.map(id => {
    const mat = parsedMaterials.value.find(m => m.id === id)
    return mat?.title || ''
  }).filter(Boolean)
  bankBuildModal.materialInfo = `已选 ${ids.length} 个素材：${names.join('、')}`
}

async function autoSuggest() {
  bankBuildModal.suggestLoading = true
  try {
    if (bankBuildModal.materialIds.length > 0) {
      // Use first material for suggestion
      const suggestion: any = await request.get(`/questions/generate/suggest/${bankBuildModal.materialIds[0]}`)
      const dist = suggestion.suggested_distribution || {}
      bankTypeDist.single_choice = dist.single_choice || 0
      bankTypeDist.multiple_choice = dist.multiple_choice || 0
      bankTypeDist.true_false = dist.true_false || 0
      bankTypeDist.fill_blank = dist.fill_blank || 0
      bankTypeDist.short_answer = dist.short_answer || 0
      bankBuildModal.difficulty = suggestion.difficulty || 3
      message.success(`AI建议：生成 ${suggestion.suggested_total} 道题目`)
    } else {
      // Default suggestion when no material selected
      bankTypeDist.single_choice = 5
      bankTypeDist.multiple_choice = 2
      bankTypeDist.true_false = 3
      bankTypeDist.fill_blank = 2
      bankTypeDist.short_answer = 3
      bankBuildModal.difficulty = 3
      message.success('已设置默认推荐配比：共15道题目')
    }
  } catch {
    message.error('获取AI建议失败')
  } finally {
    bankBuildModal.suggestLoading = false
  }
}

async function handleBankBuild() {
  const dist: Record<string, number> = {}
  for (const [k, v] of Object.entries(bankTypeDist)) {
    if (v > 0) dist[k] = v
  }
  if (Object.keys(dist).length === 0) {
    message.warning('请至少设置一种题型的数量')
    return
  }

  bankBuildModal.loading = true
  startGenProgress(bankTotalCount.value)
  try {
    let totalGenerated = 0
    const payload = {
      type_distribution: dist,
      difficulty: bankBuildModal.difficulty,
      bloom_level: bankBuildModal.bloomLevel || undefined,
      custom_prompt: bankBuildModal.customPrompt || undefined,
    }

    if (bankBuildModal.materialIds.length > 0) {
      // Generate from each selected material
      for (const matId of bankBuildModal.materialIds) {
        const result: any = await request.post(
          `/questions/generate/bank/${matId}`,
          payload,
          { timeout: 300000 },
        )
        totalGenerated += result.generated || 0
      }
    } else {
      // Free generation without material
      const result: any = await request.post(
        '/questions/generate/free',
        payload,
        { timeout: 300000 },
      )
      totalGenerated = result.generated || 0
    }

    stopGenProgress(true)
    // Small delay to show 100% before closing
    await new Promise(r => setTimeout(r, 600))
    bankBuildModal.visible = false
    bankResultModal.generated = totalGenerated
    bankResultModal.visible = true
  } catch {
    stopGenProgress(false)
    message.error('题目生成失败，请重试')
  } finally {
    bankBuildModal.loading = false
  }
}

// ---- Init ----
onMounted(() => {
  fetchQuestions()
  fetchReviewCount()
})
</script>

<style scoped>
.page-container {
  padding: 0;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.page-header h2 {
  margin: 0;
  font-size: 20px;
}
.filter-card {
  margin-bottom: 16px;
}
.main-tabs {
  margin-bottom: 16px;
}
.main-tabs :deep(.ant-tabs-tab) {
  font-size: 15px;
  padding: 8px 16px;
}
.main-tabs :deep(.ant-tabs-ink-bar) {
  background: #1f4e79;
}
.main-tabs :deep(.ant-tabs-tab-active .ant-tabs-tab-btn) {
  color: #1f4e79;
  font-weight: 600;
}
</style>
