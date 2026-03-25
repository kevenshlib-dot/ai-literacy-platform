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
        <a-row :gutter="[16, 16]">
          <a-col :flex="'280px'">
            <a-input
              v-model:value="filters.keyword"
              placeholder="搜索题干关键词"
              allow-clear
              @press-enter="fetchQuestions"
            >
              <template #prefix><SearchOutlined /></template>
            </a-input>
          </a-col>
          <a-col :flex="'140px'">
            <a-select v-model:value="filters.status" placeholder="状态" allow-clear style="width: 100%">
              <a-select-option value="draft">草稿</a-select-option>
              <a-select-option value="pending_review">待审核</a-select-option>
              <a-select-option value="approved">已通过</a-select-option>
              <a-select-option value="rejected">已拒绝</a-select-option>
              <a-select-option value="archived">已归档</a-select-option>
            </a-select>
          </a-col>
          <a-col :flex="'140px'">
            <a-select v-model:value="filters.question_type" placeholder="题型" allow-clear style="width: 100%">
              <a-select-option value="single_choice">单选题</a-select-option>
              <a-select-option value="multiple_choice">多选题</a-select-option>
              <a-select-option value="true_false">判断题</a-select-option>
              <a-select-option value="fill_blank">填空题</a-select-option>
              <a-select-option value="short_answer">简答题</a-select-option>
            </a-select>
          </a-col>
          <a-col :flex="'140px'">
            <a-select v-model:value="filters.difficulty" placeholder="难度" allow-clear style="width: 100%">
              <a-select-option :value="1">1 - 入门</a-select-option>
              <a-select-option :value="2">2 - 简单</a-select-option>
              <a-select-option :value="3">3 - 中等</a-select-option>
              <a-select-option :value="4">4 - 困难</a-select-option>
              <a-select-option :value="5">5 - 专家</a-select-option>
            </a-select>
          </a-col>
          <a-col :flex="'180px'">
            <a-select v-model:value="filters.dimension" placeholder="AI素养维度" allow-clear style="width: 100%">
              <a-select-option value="AI基础知识">AI基础知识</a-select-option>
              <a-select-option value="AI技术应用">AI技术应用</a-select-option>
              <a-select-option value="AI伦理安全">AI伦理安全</a-select-option>
              <a-select-option value="AI批判思维">AI批判思维</a-select-option>
              <a-select-option value="AI创新实践">AI创新实践</a-select-option>
            </a-select>
          </a-col>
          <a-col :flex="'240px'">
            <a-select
              v-model:value="filters.source_material_id"
              placeholder="素材"
              allow-clear
              show-search
              :loading="filterMaterialsLoading"
              :options="questionFilterMaterialOptions"
              option-filter-prop="label"
              style="width: 100%"
              @dropdown-visible-change="handleMaterialFilterDropdownVisibleChange"
            />
          </a-col>
          <a-col :flex="'auto'">
            <div class="question-filter-actions">
              <a-space wrap>
                <a-checkbox v-model:checked="filters.only_mine" @change="fetchQuestions">仅看自己</a-checkbox>
                <a-button type="primary" @click="fetchQuestions">查询</a-button>
                <a-button @click="resetFilters">重置</a-button>
              </a-space>
            </div>
          </a-col>
        </a-row>
      </a-card>

      <a-card :bordered="false" style="margin-bottom: 16px" :loading="questionStatsLoading">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap;">
          <a-space :size="24" wrap>
            <a-statistic title="题目总数" :value="questionStats?.total || 0" />
            <a-statistic title="已通过" :value="questionStats?.by_status?.approved || 0" />
            <a-statistic title="缺维度" :value="questionStats?.quality_metrics?.missing_dimension_count || 0" :value-style="{ color: '#d46b08' }" />
            <a-statistic title="缺 Bloom" :value="questionStats?.quality_metrics?.missing_bloom_level_count || 0" :value-style="{ color: '#d46b08' }" />
            <a-statistic title="缺解析" :value="questionStats?.quality_metrics?.missing_explanation_count || 0" :value-style="{ color: '#cf1322' }" />
            <a-statistic title="已关联素材" :value="questionStats?.quality_metrics?.source_linked_count || 0" />
          </a-space>
          <div v-if="questionStats?.by_bloom_level && Object.keys(questionStats.by_bloom_level).length > 0" style="max-width: 420px;">
            <div style="margin-bottom: 8px; color: #666; font-size: 13px;">认知层次分布</div>
            <a-space wrap>
              <a-tag v-for="(count, level) in questionStats.by_bloom_level" :key="level" color="geekblue">
                {{ bloomSummaryLabel(String(level)) }} {{ count }}
              </a-tag>
            </a-space>
          </div>
        </div>
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
          :scroll="{ x: 1380 }"
          :row-selection="{ selectedRowKeys, onChange: onSelectChange }"
          row-key="id"
          @change="handleTableChange"
          size="middle"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'stem'">
              <a class="stem-cell" @click="showDetail(record)">{{ record.stem }}</a>
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
            <template v-if="column.key === 'source'">
              <span class="source-cell" :title="formatQuestionSource(record)">{{ formatQuestionSource(record) }}</span>
            </template>
            <template v-if="column.key === 'status'">
              <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
            </template>
            <template v-if="column.key === 'created_at'">
              {{ formatDate(record.created_at) }}
            </template>
            <template v-if="column.key === 'actions'">
              <div class="table-action-group">
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
              </div>
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
          :scroll="{ x: 1420 }"
          :row-selection="{ selectedRowKeys: reviewSelectedKeys, onChange: onReviewSelectChange }"
          row-key="id"
          @change="handleReviewTableChange"
          size="middle"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'stem'">
              <a class="stem-cell" @click="showDetail(record)">{{ record.stem }}</a>
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
            <template v-if="column.key === 'source'">
              <span class="source-cell" :title="formatQuestionSource(record)">{{ formatQuestionSource(record) }}</span>
            </template>
            <template v-if="column.key === 'created_at'">
              {{ formatDate(record.created_at) }}
            </template>
            <template v-if="column.key === 'review_actions'">
              <div class="table-action-group">
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
              </div>
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
      :confirm-loading="submitLoading"
    >
      <template #footer>
        <div style="display: flex; justify-content: space-between;">
          <a-space v-if="editingQuestion">
            <a-button
              v-if="editingQuestion.status === 'draft'"
              style="background: #1f4e79; color: #fff; border-color: #1f4e79"
              @click="handleCreateOrUpdate().then(() => submitForReview(editingQuestion.id))"
            >保存并提交审核</a-button>
            <a-button @click="runAICheck(editingQuestion.id)" :loading="aiCheckLoading">
              <template #icon><RobotOutlined /></template>
              AI检查
            </a-button>
            <a-popconfirm
              title="确认删除该题目？"
              @confirm="deleteQuestion(editingQuestion.id); createModalVisible = false"
            >
              <a-button danger>删除</a-button>
            </a-popconfirm>
          </a-space>
          <span v-else></span>
          <a-space>
            <a-button @click="createModalVisible = false">取消</a-button>
            <a-button type="primary" :loading="submitLoading" @click="handleCreateOrUpdate">保存</a-button>
          </a-space>
        </div>
      </template>
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
      <template #footer>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <a-button
            :disabled="detailIndex <= 0"
            @click="navigateDetail(-1)"
          >
            <template #icon><LeftOutlined /></template>
            上一题
          </a-button>
          <span style="color: #999; font-size: 12px;">
            {{ detailIndex >= 0 ? `${detailIndex + 1} / ${questions.length}` : '' }}
          </span>
          <a-button
            :disabled="detailIndex < 0 || detailIndex >= questions.length - 1"
            @click="navigateDetail(1)"
          >
            下一题
            <template #icon><RightOutlined /></template>
          </a-button>
        </div>
      </template>
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
          <a-descriptions-item label="来源">{{ formatQuestionSource(detailQuestion) }}</a-descriptions-item>
          <a-descriptions-item v-if="detailQuestion.review_comment" label="审核意见">{{ detailQuestion.review_comment }}</a-descriptions-item>
          <a-descriptions-item label="创建时间">{{ formatDate(detailQuestion.created_at) }}</a-descriptions-item>
        </a-descriptions>

        <!-- Action Buttons -->
        <div style="margin-top: 16px;">
          <!-- Row 1: 互动 + 管理 -->
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <a-space>
              <a-button @click="toggleLike">
                <template #icon><LikeFilled v-if="detailInteractions.liked" /><LikeOutlined v-else /></template>
                {{ detailInteractions.like_count }}
              </a-button>
              <a-button @click="toggleFavorite">
                <template #icon><StarFilled v-if="detailInteractions.favorited" /><StarOutlined v-else /></template>
                收藏
              </a-button>
              <a-button @click="feedbackVisible = true">
                <template #icon><FlagOutlined /></template>
                反馈
              </a-button>
            </a-space>
            <a-space>
              <a-button
                v-if="detailQuestion.status === 'draft' || detailQuestion.status === 'pending_review'"
                @click="detailVisible = false; editQuestion(detailQuestion)"
              >
                <template #icon><EditOutlined /></template>编辑
              </a-button>
              <a-popconfirm title="确认删除该题目？" @confirm="deleteQuestion(detailQuestion.id); detailVisible = false">
                <a-button danger><template #icon><DeleteOutlined /></template>删除</a-button>
              </a-popconfirm>
            </a-space>
          </div>

          <!-- Divider -->
          <a-divider style="margin: 10px 0" />

          <!-- Row 2: 工作流（右对齐） -->
          <div style="display: flex; justify-content: flex-end;">
            <a-space>
              <a-button @click="runAICheck(detailQuestion.id)" :loading="aiCheckLoading">
                <template #icon><RobotOutlined /></template>AI质量检查
              </a-button>
              <a-button
                v-if="detailQuestion.status === 'draft'"
                type="primary"
                style="background: #1f4e79; border-color: #1f4e79"
                @click="submitForReview(detailQuestion.id)"
              >提交审核</a-button>
              <a-button
                v-if="detailQuestion.status === 'draft' || detailQuestion.status === 'pending_review'"
                type="primary"
                style="background: #52c41a; border-color: #52c41a"
                @click="reviewAction(detailQuestion.id, 'approve')"
              >通过</a-button>
              <a-button
                v-if="detailQuestion.status === 'draft' || detailQuestion.status === 'pending_review'"
                danger
                @click="reviewAction(detailQuestion.id, 'reject')"
              >拒绝</a-button>
            </a-space>
          </div>
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

        <a-card v-if="detailQuestion.calibration_review" title="后验校准" size="small" style="margin-top: 16px">
          <a-descriptions :column="2" size="small">
            <a-descriptions-item label="校准结论">
              <a-tag :color="detailQuestion.calibration_review.severity === 'severe' ? 'red' : detailQuestion.calibration_review.severity === 'warn' ? 'orange' : 'green'">
                {{ detailQuestion.calibration_review.severity === 'severe' ? '偏差较大' : detailQuestion.calibration_review.severity === 'warn' ? '存在偏差' : '基本一致' }}
              </a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="难度">
              声明 {{ detailQuestion.calibration_review.requested_difficulty }} / 估计 {{ detailQuestion.calibration_review.estimated_difficulty }}
            </a-descriptions-item>
            <a-descriptions-item v-if="detailQuestion.calibration_review.requested_bloom_level" label="认知层次">
              声明 {{ bloomLabel(detailQuestion.calibration_review.requested_bloom_level) }} / 估计 {{ bloomLabel(detailQuestion.calibration_review.estimated_bloom_level) }}
            </a-descriptions-item>
          </a-descriptions>
          <div v-if="detailQuestion.calibration_review.warnings?.length" style="margin-top: 8px">
            <a-tag v-for="item in detailQuestion.calibration_review.warnings" :key="item" color="orange" style="margin-bottom: 4px;">
              {{ item }}
            </a-tag>
          </div>
          <p v-if="detailQuestion.calibration_review.difficulty_reasons?.length" style="margin-top: 8px; color: #666">
            难度依据：{{ detailQuestion.calibration_review.difficulty_reasons.join('；') }}
          </p>
          <p v-if="detailQuestion.calibration_review.bloom_reasons?.length" style="color: #666">
            Bloom依据：{{ detailQuestion.calibration_review.bloom_reasons.join('；') }}
          </p>
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

    <!-- Feedback Modal -->
    <a-modal
      v-model:open="feedbackVisible"
      title="提交反馈"
      @ok="submitFeedback"
      :confirm-loading="feedbackLoading"
      :ok-button-props="{ disabled: !feedbackType }"
    >
      <a-radio-group v-model:value="feedbackType" style="margin-bottom: 12px; display: flex; flex-direction: column; gap: 8px">
        <a-radio value="error">题目有误</a-radio>
        <a-radio value="unclear">表述不清</a-radio>
        <a-radio value="wrong_answer">答案有误</a-radio>
        <a-radio value="other">其他</a-radio>
      </a-radio-group>
      <a-textarea v-model:value="feedbackComment" placeholder="补充说明（选填）" :rows="3" />
    </a-modal>

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

    <!-- AI Check Result Modal -->
    <a-modal
      v-model:open="aiResultModalVisible"
      title="AI 质量检查结果"
      :width="480"
      :footer="null"
    >
      <div v-if="aiCheckResult" style="text-align: center; padding: 16px 0;">
        <div style="margin-bottom: 16px;">
          <span
            style="font-size: 56px; font-weight: 700; line-height: 1;"
            :style="{ color: aiScore10(aiCheckResult.overall_score) <= 5 ? '#ff4d4f' : '#52c41a' }"
          >{{ aiScore10(aiCheckResult.overall_score) }}</span>
          <span style="font-size: 20px; color: #999; margin-left: 2px;">/10</span>
        </div>
        <a-tag
          :color="aiScore10(aiCheckResult.overall_score) <= 5 ? 'red' : 'green'"
          style="font-size: 16px; padding: 4px 16px;"
        >
          {{ aiScore10(aiCheckResult.overall_score) <= 5 ? '建议拒绝' : '建议通过' }}
        </a-tag>

        <div v-if="aiCheckResult.scores" style="margin-top: 20px; text-align: left;">
          <div
            v-for="(score, key) in aiCheckResult.scores"
            :key="key"
            style="display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid #f5f5f5;"
          >
            <span style="color: #666;">{{ scoreLabel(key as string) }}</span>
            <span :style="{ fontWeight: 600, color: aiScore10(score as number) <= 5 ? '#ff4d4f' : '#52c41a' }">
              {{ aiScore10(score as number) }}/10
            </span>
          </div>
        </div>

        <p v-if="aiCheckResult.comments" style="margin-top: 16px; color: #666; text-align: left; background: #fafafa; padding: 12px; border-radius: 6px;">
          {{ aiCheckResult.comments }}
        </p>

        <div style="margin-top: 24px;">
          <a-space v-if="aiScore10(aiCheckResult.overall_score) <= 5">
            <a-popconfirm title="确认删除该题目？" @confirm="aiResultDelete">
              <a-button danger type="primary">
                <template #icon><DeleteOutlined /></template>
                删除
              </a-button>
            </a-popconfirm>
            <a-button @click="aiResultModalVisible = false">保留</a-button>
          </a-space>
          <a-space v-else>
            <a-button type="primary" style="background: #52c41a; border-color: #52c41a" @click="aiResultApprove">
              <template #icon><CheckOutlined /></template>
              通过
            </a-button>
            <a-button @click="aiResultModalVisible = false">暂不操作</a-button>
          </a-space>
        </div>
      </div>
    </a-modal>

    <!-- Question Bank Build Modal -->
    <a-modal
      v-model:open="bankBuildModal.visible"
      title="新建题库 - 从素材生成试题"
      width="720px"
      @ok="handleBankBuild"
      :confirm-loading="bankBuildModal.loading"
      :ok-text="bankBuildModal.loading ? '生成中...' : '开始生成'"
    >
      <a-form layout="vertical">
        <a-form-item>
          <template #label>
            选择素材（可多选，不选则直接用AI出题）
            <span style="color: #999; font-weight: 400">（影响 &#123;&#123;content_section&#125;&#125;）</span>
          </template>
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

        <a-form-item label="知识片段策略">
          <a-radio-group v-model:value="bankBuildModal.selectionMode" button-style="solid">
            <a-radio-button value="stable">稳定优先</a-radio-button>
            <a-radio-button value="coverage">覆盖优先</a-radio-button>
          </a-radio-group>
          <div style="margin-top: 8px; color: #999; line-height: 1.6">
            稳定优先：固定条件下优先选中同一批高价值知识片段。
            覆盖优先：会参考该素材最近几次建库已命中的知识片段，对高频片段降权，提升未覆盖片段进入候选的机会。
          </div>
        </a-form-item>

        <a-form-item>
          <template #label>
            额外要求（会注入到用户提示词模板）
            <span style="color: #999; font-weight: 400">（对应 &#123;&#123;custom_requirements&#125;&#125;）</span>
          </template>
          <a-textarea
            v-model:value="bankBuildModal.customPrompt"
            placeholder="可输入对出题的特殊要求，如：侧重考察应用能力、避免过于简单的记忆题、题目需贴近实际工作场景..."
            :maxlength="500"
            show-count
            :rows="3"
          />
        </a-form-item>

        <a-card size="small" :loading="bankBuildModal.promptConfigLoading" style="margin-bottom: 16px">
          <template #title>高级提示词配置</template>
          <template #extra>
            <a-space>
              <a-tag :color="bankBuildModal.hasSavedPromptConfig ? 'processing' : 'default'">
                {{ bankBuildModal.hasSavedPromptConfig ? '使用我的默认提示词' : '使用系统默认提示词' }}
              </a-tag>
              <a-button
                size="small"
                :loading="bankBuildModal.promptPreviewLoading"
                @click="openPromptPreview"
              >
                <template #icon><EyeOutlined /></template>
                预览最终提示词
              </a-button>
              <a-tag v-if="bankBuildModal.promptPreviewDirty" color="warning">预览未刷新</a-tag>
              <a-button size="small" type="link" @click="bankBuildModal.promptConfigCollapsed = !bankBuildModal.promptConfigCollapsed">
                {{ bankBuildModal.promptConfigCollapsed ? '展开' : '收起' }}
              </a-button>
            </a-space>
          </template>

          <template v-if="!bankBuildModal.promptConfigCollapsed">
            <a-alert
              type="info"
              show-icon
              style="margin-bottom: 12px"
              :message="isUsingDefaultPromptConfig ? '当前编辑内容与系统默认一致，点击保存会清除个人默认配置。' : '当前编辑内容会直接用于本次生成；点击保存后，下次打开会自动带出。'"
            />

            <div style="display: flex; justify-content: flex-end; margin-bottom: 12px;">
              <a-space>
                <a-button size="small" @click="resetPromptEditorsToDefaults">
                  <template #icon><UndoOutlined /></template>
                  恢复系统默认
                </a-button>
                <a-button
                  size="small"
                  type="primary"
                  :loading="bankBuildModal.promptSaveLoading"
                  @click="savePromptConfig"
                >
                  <template #icon><SaveOutlined /></template>
                  保存为我的默认提示词
                </a-button>
              </a-space>
            </div>

            <a-form-item label="系统提示词" style="margin-bottom: 12px">
              <a-textarea
                v-model:value="bankBuildModal.systemPrompt"
                :maxlength="20000"
                show-count
                :auto-size="{ minRows: 8, maxRows: 16 }"
                placeholder="请输入系统提示词"
              />
            </a-form-item>

            <a-form-item label="用户提示词模板" style="margin-bottom: 12px">
              <a-textarea
                v-model:value="bankBuildModal.userPromptTemplate"
                :maxlength="20000"
                show-count
                :auto-size="{ minRows: 10, maxRows: 18 }"
                placeholder="请输入用户提示词模板，支持占位符"
              />
            </a-form-item>

            <div>
              <div style="font-weight: 600; margin-bottom: 8px">可用占位符</div>
              <a-space wrap>
                <a-tag
                  v-for="item in bankBuildModal.promptPlaceholders"
                  :key="item.key"
                  color="blue"
                  style="cursor: pointer"
                  @click="copyPromptPlaceholder(item.key)"
                >
                  <CopyOutlined />
                  {{ item.key }} - {{ item.description }}（来源：{{ item.source }}）
                </a-tag>
              </a-space>
            </div>
          </template>
        </a-card>

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

        <a-form-item>
          <template #label>
            题型分配
            <span style="color: #999; font-weight: 400">（影响 &#123;&#123;count&#125;&#125; 和 &#123;&#123;question_types&#125;&#125;）</span>
          </template>
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
            <a-form-item>
              <template #label>
                难度等级
                <span style="color: #999; font-weight: 400">（影响 &#123;&#123;difficulty_section&#125;&#125;）</span>
              </template>
              <a-slider v-model:value="bankBuildModal.difficulty" :min="1" :max="5" :marks="{1:'入门',3:'中等',5:'专家'}" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item>
              <template #label>
                认知层次（可选）
                <span style="color: #999; font-weight: 400">（影响 &#123;&#123;bloom_section&#125;&#125;）</span>
              </template>
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

        <a-form-item label="优先使用知识片段数">
          <a-input-number
            v-model:value="bankBuildModal.maxUnits"
            :min="1"
            :max="50"
            style="width: 100%"
          />
          <div style="margin-top: 6px; color: #8c8c8c; font-size: 12px; line-height: 1.5;">
            系统会优先按该数量选取知识片段；若目标题量超过该值，会自动扩展候选片段，以保证每题使用不同知识点。
          </div>
        </a-form-item>
      </a-form>

      <div v-if="bankBuildModal.loading" style="margin-top: 16px">
        <!-- LLM Model Info -->
        <div class="gen-model-info">
          <RobotOutlined class="gen-robot-icon" />
          <span class="gen-model-name">{{ genModelName || 'AI' }} 正在生成...</span>
        </div>
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

    <a-modal
      v-model:open="promptPreviewModal.visible"
      title="最终用户提示词预览（按实际调用拆分）"
      width="920px"
      :confirm-loading="bankBuildModal.promptPreviewLoading"
      ok-text="关闭"
      @ok="promptPreviewModal.visible = false"
      :cancel-button-props="{ style: { display: 'none' } }"
    >
      <div v-if="bankBuildModal.promptPreviewLoading" style="padding: 24px 0; text-align: center;">
        <a-spin tip="正在生成预览..." />
      </div>
      <template v-else>
        <a-alert
          v-if="promptPreviewModal.note"
          type="info"
          show-icon
          :message="promptPreviewModal.note"
          style="margin-bottom: 12px"
        />
        <a-empty
          v-if="!promptPreviewModal.items.length"
          description="暂无预览内容"
        />
        <div v-else style="display: flex; flex-direction: column; gap: 12px; max-height: 65vh; overflow: auto; padding-right: 4px;">
          <div
            v-for="(item, index) in promptPreviewModal.items"
            :key="`${index}-${item.title}`"
          >
            <div style="font-weight: 600; margin-bottom: 6px;">{{ item.title }}</div>
            <a-textarea
              :value="item.rendered_user_prompt"
              readonly
              :auto-size="{ minRows: 6, maxRows: 14 }"
            />
          </div>
        </div>
      </template>
    </a-modal>

    <!-- Generation Result Modal -->
    <a-modal
      v-model:open="bankResultModal.visible"
      title="试题生成完成"
      width="520px"
      @ok="closeBankResult"
      ok-text="确定"
      :cancel-button-props="{ style: { display: 'none' } }"
    >
      <div style="text-align: center; padding: 8px 0 16px;">
        <CheckCircleOutlined style="font-size: 48px; color: #52c41a;" />
        <h3 style="margin: 12px 0 4px; font-size: 20px; font-weight: 600;">
          成功生成 {{ bankResultModal.generated }} 道试题
        </h3>
        <p style="color: #999; margin: 0;">所有题目已保存为草稿状态</p>
      </div>

      <!-- Stats Report -->
      <div class="gen-report-section">
        <div class="gen-report-title">📊 生成报告</div>
        <div class="gen-report-card">
          <div class="gen-report-row">
            <span class="gen-report-label">模型</span>
            <span class="gen-report-value">{{ bankResultModal.modelName || '-' }}</span>
          </div>
          <div class="gen-report-row">
            <span class="gen-report-label">耗时</span>
            <span class="gen-report-value">{{ bankResultModal.durationText || '-' }}</span>
          </div>
          <div class="gen-report-row">
            <span class="gen-report-label">Token 消耗</span>
            <span class="gen-report-value">{{ bankResultModal.totalTokens?.toLocaleString() || '-' }}</span>
          </div>
          <div v-if="bankResultModal.promptTokens || bankResultModal.completionTokens" class="gen-report-row" style="padding-left: 16px;">
            <span class="gen-report-label" style="color: #aaa; font-size: 12px;">输入 / 输出</span>
            <span class="gen-report-value" style="color: #aaa; font-size: 12px;">
              {{ bankResultModal.promptTokens?.toLocaleString() || '0' }} / {{ bankResultModal.completionTokens?.toLocaleString() || '0' }}
            </span>
          </div>
        </div>
      </div>

      <div v-if="bankResultModal.typeCounts && Object.keys(bankResultModal.typeCounts).length > 0" class="gen-report-section">
        <div class="gen-report-title">📝 题型分布</div>
        <div class="gen-report-card">
          <div
            v-for="(count, qtype) in bankResultModal.typeCounts"
            :key="qtype"
            class="gen-type-row"
          >
            <span class="gen-type-label">{{ typeLabel(qtype as string) }}</span>
            <span class="gen-type-count">{{ count }} 题</span>
            <div class="gen-type-bar-bg">
              <div
                class="gen-type-bar"
                :style="{ width: Math.round(((count as number) / bankResultModal.generated) * 100) + '%' }"
              ></div>
            </div>
            <span class="gen-type-pct">{{ Math.round(((count as number) / bankResultModal.generated) * 100) }}%</span>
          </div>
        </div>
      </div>
    </a-modal>

    <!-- Preview & Review Drawer -->
    <a-drawer
      v-model:open="previewDrawerVisible"
      title="题目预览 - 审阅后保存"
      :width="1100"
      :mask-closable="false"
      :closable="true"
      @close="onPreviewDrawerClose"
    >
      <!-- Action Bar -->
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 8px;">
        <a-space>
          <a-tag color="blue" style="font-size: 14px; padding: 4px 12px;">共 {{ previewQuestions.length }} 道题目</a-tag>
          <a-button
            size="small"
            danger
            :disabled="previewSelectedKeys.length === 0"
            @click="removeSelectedPreview"
          >
            <template #icon><DeleteOutlined /></template>
            删除选中 ({{ previewSelectedKeys.length }})
          </a-button>
        </a-space>
        <a-space>
          <a-button @click="openCandidateSelector">
            <template #icon><PlusOutlined /></template>
            从题库添加
          </a-button>
          <a-button
            type="primary"
            :loading="previewSaving"
            @click="savePreviewQuestions"
            :disabled="previewQuestions.length === 0"
            style="background: #1f4e79; border-color: #1f4e79"
          >
            <template #icon><CheckOutlined /></template>
            确认保存 ({{ previewQuestions.length }} 题)
          </a-button>
        </a-space>
      </div>

      <!-- Preview Stats Summary -->
      <div v-if="previewStats" style="margin-bottom: 12px;">
        <a-alert
          v-if="previewWarnings.length > 0"
          type="warning"
          show-icon
          :message="previewHasQualityRisk ? '当前预览包含质量风险，仍可保存为草稿，建议先审阅。' : '当前预览包含质量提醒。'"
          :description="previewWarnings.join('；')"
          style="margin-bottom: 12px"
        />
        <a-space :size="16">
          <span style="color: #666; font-size: 13px;">模型: <b>{{ previewStats.modelName || '-' }}</b></span>
          <span style="color: #666; font-size: 13px;">耗时: <b>{{ previewStats.durationText || '-' }}</b></span>
          <span style="color: #666; font-size: 13px;">Token: <b>{{ previewStats.totalTokens?.toLocaleString() || '-' }}</b></span>
          <span style="color: #666; font-size: 13px;">目标 / 实际: <b>{{ previewStats.requestedTotal || 0 }} / {{ previewStats.generatedTotal || previewQuestions.length }}</b></span>
          <span v-if="previewStats.selectedUnitCount" style="color: #666; font-size: 13px;">
            知识片段设置 / 实际选片:
            <b>{{ previewStats.configuredMaxUnits || 0 }} / {{ previewStats.selectedUnitCount }}</b>
          </span>
          <span v-if="previewStats.nearDuplicateCount" style="color: #d46b08; font-size: 13px;">近重复: <b>{{ previewStats.nearDuplicateCount }}</b></span>
          <span v-if="previewStats.existingNearDuplicateCount" style="color: #cf1322; font-size: 13px;">题库近重复: <b>{{ previewStats.existingNearDuplicateCount }}</b></span>
          <span v-if="previewStats.difficultyMismatchCount" style="color: #d46b08; font-size: 13px;">难度偏差: <b>{{ previewStats.difficultyMismatchCount }}</b></span>
          <span v-if="previewStats.bloomMismatchCount" style="color: #d46b08; font-size: 13px;">Bloom偏差: <b>{{ previewStats.bloomMismatchCount }}</b></span>
          <span v-if="previewStats.fallbackCount" style="color: #d46b08; font-size: 13px;">降级次数: <b>{{ previewStats.fallbackCount }}</b></span>
        </a-space>
      </div>

      <!-- Preview Table -->
      <a-table
        :columns="previewColumns"
        :data-source="previewQuestions"
        :row-selection="{ selectedRowKeys: previewSelectedKeys, onChange: (keys: string[]) => { previewSelectedKeys = keys } }"
        row-key="_uid"
        :pagination="{ pageSize: 50, showTotal: (total: number) => `共 ${total} 道` }"
        size="middle"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'stem'">
            <a class="stem-cell" @click="showPreviewDetail(record)">{{ record.stem }}</a>
            <a-tag v-if="record._fromExisting" color="gold" style="margin-left: 4px; font-size: 11px;">已有</a-tag>
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
          <template v-if="column.key === 'correct_answer'">
            <span style="color: #52c41a; font-weight: 600;">{{ record.correct_answer }}</span>
          </template>
          <template v-if="column.key === 'preview_actions'">
            <a-space>
              <a-button size="small" type="link" @click="showPreviewDetail(record)">
                <template #icon><EyeOutlined /></template>
              </a-button>
              <a-popconfirm title="确认移除此题？" @confirm="removePreviewQuestion(record._uid)">
                <a-button size="small" type="link" danger>
                  <template #icon><DeleteOutlined /></template>
                </a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-drawer>

    <!-- Candidate Question Selector Modal -->
    <a-modal
      v-model:open="candidateSelectorVisible"
      title="从已有题库添加题目"
      width="960px"
      @ok="addCandidatesToPreview"
      ok-text="添加选中"
      :ok-button-props="{ disabled: candidateSelectedKeys.length === 0 }"
    >
      <a-row :gutter="8" style="margin-bottom: 12px">
        <a-col :span="7">
          <a-input
            v-model:value="candidateFilters.keyword"
            placeholder="搜索题干关键词"
            allow-clear
            @press-enter="fetchCandidateQuestions"
          >
            <template #prefix><SearchOutlined /></template>
          </a-input>
        </a-col>
        <a-col :span="5">
          <a-select v-model:value="candidateFilters.question_type" placeholder="题型" allow-clear style="width: 100%" @change="fetchCandidateQuestions">
            <a-select-option value="single_choice">单选题</a-select-option>
            <a-select-option value="multiple_choice">多选题</a-select-option>
            <a-select-option value="true_false">判断题</a-select-option>
            <a-select-option value="fill_blank">填空题</a-select-option>
            <a-select-option value="short_answer">简答题</a-select-option>
          </a-select>
        </a-col>
        <a-col :span="5">
          <a-select v-model:value="candidateFilters.dimension" placeholder="维度" allow-clear style="width: 100%" @change="fetchCandidateQuestions">
            <a-select-option value="AI基础知识">AI基础知识</a-select-option>
            <a-select-option value="AI技术应用">AI技术应用</a-select-option>
            <a-select-option value="AI伦理安全">AI伦理安全</a-select-option>
            <a-select-option value="AI批判思维">AI批判思维</a-select-option>
            <a-select-option value="AI创新实践">AI创新实践</a-select-option>
          </a-select>
        </a-col>
        <a-col :span="3">
          <a-button type="primary" @click="fetchCandidateQuestions">查询</a-button>
        </a-col>
        <a-col :span="4" style="text-align: right;">
          <span v-if="candidateSelectedKeys.length > 0" style="color: #1f4e79; font-weight: 500;">
            已选 {{ candidateSelectedKeys.length }} 题
          </span>
        </a-col>
      </a-row>

      <a-table
        :columns="candidateColumns"
        :data-source="candidateQuestions"
        :loading="candidateLoading"
        :row-selection="{ selectedRowKeys: candidateSelectedKeys, onChange: (keys: string[]) => { candidateSelectedKeys = keys } }"
        row-key="id"
        :pagination="candidatePagination"
        @change="handleCandidateTableChange"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'stem'">
            <a class="stem-cell">{{ record.stem }}</a>
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
        </template>
      </a-table>
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
import { ref, reactive, computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
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
  EditOutlined,
  DeleteOutlined,
  SaveOutlined,
  CopyOutlined,
  UndoOutlined,
  LeftOutlined,
  RightOutlined,
  LikeOutlined,
  LikeFilled,
  StarOutlined,
  StarFilled,
  FlagOutlined,
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import request from '@/utils/request'

// ---- State ----
const loading = ref(false)
const submitLoading = ref(false)
const aiCheckLoading = ref(false)
const questionStatsLoading = ref(false)
const questions = ref<any[]>([])
const questionStats = ref<any>(null)
const selectedRowKeys = ref<string[]>([])
const createModalVisible = ref(false)
const detailVisible = ref(false)
const reviewModalVisible = ref(false)
const editingQuestion = ref<any>(null)
const detailQuestion = ref<any>(null)
const detailInteractions = reactive({ liked: false, favorited: false, like_count: 0, favorite_count: 0 })
const feedbackVisible = ref(false)
const feedbackType = ref('')
const feedbackComment = ref('')
const feedbackLoading = ref(false)
const aiCheckResult = ref<any>(null)
const aiResultModalVisible = ref(false)
const aiCheckQuestionId = ref('')
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
  source_material_id: undefined as string | undefined,
  only_mine: false,
})

const filterMaterialsLoading = ref(false)
const filterMaterialsLoaded = ref(false)
const filterMaterials = ref<any[]>([])
const questionFilterMaterialOptions = computed(() =>
  filterMaterials.value.map((item: any) => ({
    label: item.title,
    value: item.id,
  }))
)

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
  { title: '题干', key: 'stem', dataIndex: 'stem', width: 320 },
  { title: '题型', key: 'question_type', dataIndex: 'question_type', width: 90 },
  { title: '难度', key: 'difficulty', dataIndex: 'difficulty', width: 140 },
  { title: '维度', key: 'dimension', dataIndex: 'dimension', width: 120, ellipsis: true },
  { title: '来源', key: 'source', width: 240, ellipsis: true },
  { title: '状态', key: 'status', dataIndex: 'status', width: 90 },
  { title: '创建时间', key: 'created_at', dataIndex: 'created_at', width: 120 },
  { title: '操作', key: 'actions', width: 200, fixed: 'right' as const },
]

// ---- Review Tab Columns ----
const reviewColumns = [
  { title: '题干', key: 'stem', dataIndex: 'stem', width: 340 },
  { title: '题型', key: 'question_type', dataIndex: 'question_type', width: 90 },
  { title: '难度', key: 'difficulty', dataIndex: 'difficulty', width: 140 },
  { title: '维度', key: 'dimension', dataIndex: 'dimension', width: 120, ellipsis: true },
  { title: '认知层次', key: 'bloom_level', dataIndex: 'bloom_level', width: 90 },
  { title: '来源', key: 'source', width: 240, ellipsis: true },
  { title: '创建时间', key: 'created_at', dataIndex: 'created_at', width: 110 },
  { title: '操作', key: 'review_actions', width: 260, fixed: 'right' as const },
]

// ---- Preview Table Columns ----
const previewColumns = [
  { title: '题干', key: 'stem', dataIndex: 'stem', width: 300 },
  { title: '题型', key: 'question_type', dataIndex: 'question_type', width: 90 },
  { title: '难度', key: 'difficulty', dataIndex: 'difficulty', width: 140 },
  { title: '维度', key: 'dimension', dataIndex: 'dimension', width: 120, ellipsis: true },
  { title: '答案', key: 'correct_answer', dataIndex: 'correct_answer', width: 80 },
  { title: '操作', key: 'preview_actions', width: 100 },
]

// ---- Candidate Table Columns ----
const candidateColumns = [
  { title: '题干', key: 'stem', dataIndex: 'stem', width: 280 },
  { title: '题型', key: 'question_type', dataIndex: 'question_type', width: 90 },
  { title: '难度', key: 'difficulty', dataIndex: 'difficulty', width: 140 },
  { title: '维度', key: 'dimension', dataIndex: 'dimension', width: 120, ellipsis: true },
  { title: '状态', key: 'status', dataIndex: 'status', width: 90 },
  { title: '创建时间', key: 'created_at', dataIndex: 'created_at', width: 110 },
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
function bloomSummaryLabel(b: string) { return b ? bloomLabel(b) : '未标注' }
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
function formatDate(d: string) {
  if (!d) return '-'
  const dt = new Date(d)
  const M = String(dt.getMonth() + 1).padStart(2, '0')
  const D = String(dt.getDate()).padStart(2, '0')
  const h = String(dt.getHours()).padStart(2, '0')
  const m = String(dt.getMinutes()).padStart(2, '0')
  return `${M}-${D} ${h}:${m}`
}

function formatQuestionSource(question: any) {
  const materialTitle = question?.source_material_title?.trim?.() || ''
  const knowledgeUnitTitle = question?.source_knowledge_unit_title?.trim?.() || ''
  const materialId = question?.source_material_id || ''
  const knowledgeUnitId = question?.source_knowledge_unit_id || ''

  if (knowledgeUnitTitle) {
    return knowledgeUnitTitle
  }
  if (materialTitle) {
    return materialTitle
  }
  if (materialId && knowledgeUnitId) {
    return `素材ID: ${materialId} / 知识单元ID: ${knowledgeUnitId}`
  }
  if (knowledgeUnitId) {
    return `知识单元ID: ${knowledgeUnitId}`
  }
  if (materialId) {
    return `素材ID: ${materialId}`
  }
  return 'AI自由生成'
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
    if (filters.source_material_id) params.source_material_id = filters.source_material_id
    if (filters.only_mine) params.only_mine = true

    const [data, statsData]: any[] = await Promise.all([
      request.get('/questions', { params }),
      fetchQuestionStats(params),
    ])
    questions.value = data.items || []
    pagination.total = data.total || 0
    questionStats.value = statsData
  } catch (e) {
    message.error('加载题目列表失败')
  } finally {
    loading.value = false
  }
}

async function fetchQuestionStats(baseParams?: Record<string, any>) {
  questionStatsLoading.value = true
  try {
    const params = { ...(baseParams || {}) }
    delete params.skip
    delete params.limit
    return await request.get('/questions/stats', { params }) as any
  } finally {
    questionStatsLoading.value = false
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
  filters.source_material_id = undefined
  filters.only_mine = false
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

async function loadInteractions(qid: string) {
  try {
    const data: any = await request.get(`/questions/${qid}/interactions`)
    Object.assign(detailInteractions, data)
  } catch {
    // ignore
  }
}

async function showDetail(q: any) {
  detailQuestion.value = q
  aiCheckResult.value = null
  detailVisible.value = true
  await Promise.all([loadReviewHistory(q.id), loadInteractions(q.id)])
}

const detailIndex = computed(() =>
  detailQuestion.value ? questions.value.findIndex(q => q.id === detailQuestion.value.id) : -1
)

async function navigateDetail(offset: number) {
  const idx = detailIndex.value + offset
  if (idx >= 0 && idx < questions.value.length) {
    await showDetail(questions.value[idx])
  }
}

async function loadReviewHistory(qid: string) {
  try {
    reviewHistory.value = await request.get(`/questions/${qid}/review-history`) as any
  } catch {
    reviewHistory.value = []
  }
}

async function toggleLike() {
  if (!detailQuestion.value) return
  const data: any = await request.post(`/questions/${detailQuestion.value.id}/like`)
  detailInteractions.liked = data.liked
  detailInteractions.like_count = data.like_count
}

async function toggleFavorite() {
  if (!detailQuestion.value) return
  const data: any = await request.post(`/questions/${detailQuestion.value.id}/favorite`)
  detailInteractions.favorited = data.favorited
  detailInteractions.favorite_count = data.favorite_count
}

async function submitFeedback() {
  if (!detailQuestion.value || !feedbackType.value) return
  feedbackLoading.value = true
  try {
    await request.post(`/questions/${detailQuestion.value.id}/feedback`, {
      feedback_type: feedbackType.value,
      comment: feedbackComment.value || null,
    })
    message.success('反馈已提交')
    feedbackVisible.value = false
    feedbackType.value = ''
    feedbackComment.value = ''
  } catch {
    message.error('提交失败，请重试')
  } finally {
    feedbackLoading.value = false
  }
}

async function runAICheck(id: string) {
  aiCheckLoading.value = true
  try {
    aiCheckResult.value = await request.post(`/questions/${id}/ai-check`)
    aiCheckQuestionId.value = id
    aiResultModalVisible.value = true
    await loadReviewHistory(id)
  } catch (e) {
    message.error('AI检查失败')
  } finally {
    aiCheckLoading.value = false
  }
}

function aiScore10(score5: number): number {
  return Math.round(score5 * 2)
}

async function aiResultApprove() {
  aiResultModalVisible.value = false
  try {
    await request.post(`/questions/${aiCheckQuestionId.value}/review`, { action: 'approve', comment: 'AI检查通过' })
    message.success('已通过')
    if (activeTab.value === 'review') {
      await fetchReviewQuestions()
    } else {
      fetchQuestions()
    }
    if (detailQuestion.value?.id === aiCheckQuestionId.value) {
      detailQuestion.value.status = 'approved'
    }
  } catch (e) {
    message.error('操作失败')
  }
}

async function aiResultDelete() {
  aiResultModalVisible.value = false
  try {
    await request.delete(`/questions/${aiCheckQuestionId.value}`)
    message.success('题目已删除')
    detailVisible.value = false
    if (activeTab.value === 'review') {
      await fetchReviewQuestions()
    } else {
      fetchQuestions()
    }
  } catch (e) {
    message.error('删除失败')
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
    if (filters.source_material_id) params.source_material_id = filters.source_material_id

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

async function loadFilterMaterials() {
  if (filterMaterialsLoading.value || filterMaterialsLoaded.value) return

  filterMaterialsLoading.value = true
  try {
    const items: any[] = []
    const pageSize = 100
    let skip = 0
    let total = 0

    while (true) {
      const data: any = await request.get('/materials', {
        params: { skip, limit: pageSize },
      })
      const pageItems = data.data || []
      items.push(...pageItems)
      total = data.total || items.length

      if (pageItems.length === 0 || items.length >= total) break
      skip += pageItems.length
    }

    filterMaterials.value = Array.from(
      new Map(items.map((item: any) => [item.id, item])).values()
    )
    filterMaterialsLoaded.value = true
  } catch {
    filterMaterials.value = []
    message.error('加载素材列表失败')
  } finally {
    filterMaterialsLoading.value = false
  }
}

function handleMaterialFilterDropdownVisibleChange(open: boolean) {
  if (open) {
    loadFilterMaterials()
  }
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
type PromptPlaceholder = {
  key: string
  description: string
  source: string
}

type PromptDefaults = {
  system_prompt: string
  user_prompt_template: string
}

type RenderedPromptPreview = {
  title: string
  rendered_user_prompt: string
}

const bankBuildModal = reactive({
  visible: false,
  loading: false,
  suggestLoading: false,
  materialsLoading: false,
  promptConfigLoading: false,
  promptSaveLoading: false,
  promptPreviewLoading: false,
  promptConfigCollapsed: true,
  materialIds: [] as string[],
  materialInfo: null as string | null,
  selectionMode: 'stable' as 'stable' | 'coverage',
  difficulty: 3,
  bloomLevel: undefined as string | undefined,
  maxUnits: 10,
  customPrompt: '',
  systemPrompt: '',
  userPromptTemplate: '',
  hasSavedPromptConfig: false,
  promptDefaults: {
    system_prompt: '',
    user_prompt_template: '',
  } as PromptDefaults,
  promptPlaceholders: [] as PromptPlaceholder[],
  promptPreviewDirty: false,
  promptSeed: undefined as number | undefined,
})

const promptPreviewModal = reactive({
  visible: false,
  items: [] as RenderedPromptPreview[],
  note: '',
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
  modelName: '' as string,
  durationText: '' as string,
  totalTokens: 0 as number,
  promptTokens: 0 as number,
  completionTokens: 0 as number,
  typeCounts: {} as Record<string, number>,
})

const genModelName = ref('')

// ---- Preview & Review State ----
const previewDrawerVisible = ref(false)
const previewQuestions = ref<any[]>([])
const previewSelectedKeys = ref<string[]>([])
const previewSaving = ref(false)
const previewStats = ref<any>(null)
const previewWarnings = computed(() => {
  if (!previewStats.value?.warnings) return []
  return (previewStats.value.warnings as string[]).filter(Boolean)
})
const previewHasQualityRisk = computed(() => (
  !!previewStats.value?.qualityGateFailed || previewWarnings.value.length > 0
))

// Candidate selector
const candidateSelectorVisible = ref(false)
const candidateQuestions = ref<any[]>([])
const candidateSelectedKeys = ref<string[]>([])
const candidateLoading = ref(false)
const candidateFilters = reactive({
  keyword: '',
  question_type: undefined as string | undefined,
  dimension: undefined as string | undefined,
})
const candidatePagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条`,
})

let previewUidCounter = 0
function assignPreviewUid(item: any) {
  item._uid = `preview_${++previewUidCounter}`
  return item
}

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
const QUESTION_TYPE_KEYS = [
  'single_choice',
  'multiple_choice',
  'true_false',
  'fill_blank',
  'short_answer',
] as const

type MaterialSuggestion = {
  materialId: string
  materialTitle: string
  totalUnits: number
  configuredMaxUnits: number
  effectiveMaxUnits: number
  suggestedDistribution: Record<string, number>
  suggestedTotal: number
  difficulty: number
  weight: number
}

type MaterialGenerationPlan = {
  materialId: string
  materialTitle: string
  typeDistribution: Record<string, number>
}

const bankTotalCount = computed(() => {
  return Object.values(bankTypeDist).reduce((sum, v) => sum + (v || 0), 0)
})

function buildPositiveTypeDistribution() {
  const dist: Record<string, number> = {}
  for (const [key, value] of Object.entries(bankTypeDist)) {
    if (value > 0) dist[key] = value
  }
  return dist
}

function createEmptyTypeDistribution(): Record<(typeof QUESTION_TYPE_KEYS)[number], number> {
  const dist = {} as Record<(typeof QUESTION_TYPE_KEYS)[number], number>
  for (const key of QUESTION_TYPE_KEYS) dist[key] = 0
  return dist
}

function sumTypeDistribution(dist: Record<string, number>) {
  return Object.values(dist).reduce((sum, value) => sum + (value || 0), 0)
}

function allocateCountsByWeights(total: number, weightedItems: Array<{ key: string; weight: number }>) {
  const allocations: Record<string, number> = {}
  if (total <= 0 || weightedItems.length === 0) return allocations

  const normalized = weightedItems.map((item, index) => ({
    ...item,
    index,
    weight: item.weight > 0 ? item.weight : 1,
  }))
  const totalWeight = normalized.reduce((sum, item) => sum + item.weight, 0)
  const raws = normalized.map(item => ({
    ...item,
    raw: (total * item.weight) / totalWeight,
    count: Math.floor((total * item.weight) / totalWeight),
  }))

  for (const item of raws) allocations[item.key] = item.count

  let remainder = total - raws.reduce((sum, item) => sum + item.count, 0)
  raws.sort((a, b) => {
    const fracDiff = (b.raw - b.count) - (a.raw - a.count)
    if (Math.abs(fracDiff) > 1e-9) return fracDiff
    const weightDiff = b.weight - a.weight
    if (Math.abs(weightDiff) > 1e-9) return weightDiff
    return a.index - b.index
  })

  for (let i = 0; i < remainder; i += 1) {
    const target = raws[i % raws.length]
    if (!target) continue
    allocations[target.key] = (allocations[target.key] || 0) + 1
  }

  return allocations
}

async function fetchMaterialSuggestions(materialIds: string[]): Promise<MaterialSuggestion[]> {
  return Promise.all(materialIds.map(async materialId => {
    try {
      const suggestion: any = await request.get(`/questions/generate/suggest/${materialId}`, {
        params: {
          max_units: bankBuildModal.maxUnits,
          selection_mode: bankBuildModal.selectionMode,
        },
      })
      const suggestedDistribution = suggestion.suggested_distribution || {}
      const suggestedTotal = suggestion.suggested_total || sumTypeDistribution(suggestedDistribution)
      const totalUnits = suggestion.total_units || 1
      return {
        materialId,
        materialTitle: suggestion.material_title || parsedMaterials.value.find(item => item.id === materialId)?.title || materialId,
        totalUnits,
        configuredMaxUnits: suggestion.configured_max_units || bankBuildModal.maxUnits,
        effectiveMaxUnits: suggestion.effective_max_units || totalUnits,
        suggestedDistribution,
        suggestedTotal,
        difficulty: suggestion.difficulty || 3,
        weight: Math.max(suggestedTotal || totalUnits || 1, 1),
      }
    } catch {
      return {
        materialId,
        materialTitle: parsedMaterials.value.find(item => item.id === materialId)?.title || materialId,
        totalUnits: 1,
        configuredMaxUnits: bankBuildModal.maxUnits,
        effectiveMaxUnits: 1,
        suggestedDistribution: createEmptyTypeDistribution(),
        suggestedTotal: 1,
        difficulty: bankBuildModal.difficulty || 3,
        weight: 1,
      }
    }
  }))
}

function buildMaterialGenerationPlans(
  materialIds: string[],
  totalDistribution: Record<string, number>,
  suggestions: MaterialSuggestion[],
): MaterialGenerationPlan[] {
  const suggestionMap = new Map(suggestions.map(item => [item.materialId, item]))
  const planMap = new Map<string, Record<string, number>>(
    materialIds.map(materialId => [materialId, createEmptyTypeDistribution()]),
  )

  for (const [questionType, totalCount] of Object.entries(totalDistribution)) {
    const allocation = allocateCountsByWeights(
      totalCount,
      materialIds.map(materialId => ({
        key: materialId,
        weight: suggestionMap.get(materialId)?.weight || 1,
      })),
    )
    for (const materialId of materialIds) {
      const assigned = allocation[materialId] || 0
      if (assigned > 0) {
        planMap.get(materialId)![questionType] = assigned
      }
    }
  }

  return materialIds
    .map(materialId => {
      const rawDistribution = planMap.get(materialId) || {}
      const typeDistribution: Record<string, number> = {}
      for (const [questionType, count] of Object.entries(rawDistribution)) {
        if (count > 0) typeDistribution[questionType] = count
      }
      return {
        materialId,
        materialTitle: suggestionMap.get(materialId)?.materialTitle
          || parsedMaterials.value.find(item => item.id === materialId)?.title
          || materialId,
        typeDistribution,
      }
    })
    .filter(plan => sumTypeDistribution(plan.typeDistribution) > 0)
}

const isUsingDefaultPromptConfig = computed(() => (
  bankBuildModal.systemPrompt === bankBuildModal.promptDefaults.system_prompt
  && bankBuildModal.userPromptTemplate === bankBuildModal.promptDefaults.user_prompt_template
))

function filterMaterialOption(input: string, option: any) {
  return (option?.children?.[0]?.children || '').toLowerCase().includes(input.toLowerCase())
}

async function loadPromptConfig() {
  bankBuildModal.promptConfigLoading = true
  try {
    const data: any = await request.get('/questions/generation/prompt-config')
    bankBuildModal.systemPrompt = data.system_prompt || ''
    bankBuildModal.userPromptTemplate = data.user_prompt_template || ''
    bankBuildModal.hasSavedPromptConfig = !!data.has_saved_config
    bankBuildModal.promptDefaults = {
      system_prompt: data.defaults?.system_prompt || '',
      user_prompt_template: data.defaults?.user_prompt_template || '',
    }
    bankBuildModal.promptPlaceholders = data.placeholders || []
  } catch {
    message.error('加载提示词配置失败')
  } finally {
    bankBuildModal.promptConfigLoading = false
  }
}

function resetPromptEditorsToDefaults() {
  bankBuildModal.systemPrompt = bankBuildModal.promptDefaults.system_prompt || ''
  bankBuildModal.userPromptTemplate = bankBuildModal.promptDefaults.user_prompt_template || ''
}

function clearPromptPreview(markDirty = false) {
  bankBuildModal.promptPreviewDirty = markDirty
  bankBuildModal.promptSeed = undefined
  promptPreviewModal.items = []
  promptPreviewModal.note = ''
}

function buildPromptPreviewPayload() {
  return {
    type_distribution: buildPositiveTypeDistribution(),
    difficulty: bankBuildModal.difficulty,
    bloom_level: bankBuildModal.bloomLevel || undefined,
    max_units: bankBuildModal.maxUnits,
    selection_mode: bankBuildModal.selectionMode,
    custom_prompt: bankBuildModal.customPrompt || undefined,
    system_prompt: bankBuildModal.systemPrompt.trim() || undefined,
    user_prompt_template: bankBuildModal.userPromptTemplate.trim() || undefined,
    material_ids: bankBuildModal.materialIds,
  }
}

async function savePromptConfig() {
  if (!bankBuildModal.systemPrompt.trim() || !bankBuildModal.userPromptTemplate.trim()) {
    message.warning('系统提示词和用户提示词模板不能为空')
    return
  }

  bankBuildModal.promptSaveLoading = true
  try {
    if (isUsingDefaultPromptConfig.value) {
      const data: any = await request.delete('/questions/generation/prompt-config')
      bankBuildModal.hasSavedPromptConfig = !!data.has_saved_config
      bankBuildModal.promptDefaults = {
        system_prompt: data.defaults?.system_prompt || bankBuildModal.promptDefaults.system_prompt,
        user_prompt_template: data.defaults?.user_prompt_template || bankBuildModal.promptDefaults.user_prompt_template,
      }
      bankBuildModal.promptPlaceholders = data.placeholders || bankBuildModal.promptPlaceholders
      bankBuildModal.systemPrompt = data.system_prompt || bankBuildModal.systemPrompt
      bankBuildModal.userPromptTemplate = data.user_prompt_template || bankBuildModal.userPromptTemplate
      message.success('已恢复为系统默认提示词')
      return
    }

    const data: any = await request.put('/questions/generation/prompt-config', {
      system_prompt: bankBuildModal.systemPrompt,
      user_prompt_template: bankBuildModal.userPromptTemplate,
    })
    bankBuildModal.hasSavedPromptConfig = !!data.has_saved_config
    bankBuildModal.promptDefaults = {
      system_prompt: data.defaults?.system_prompt || bankBuildModal.promptDefaults.system_prompt,
      user_prompt_template: data.defaults?.user_prompt_template || bankBuildModal.promptDefaults.user_prompt_template,
    }
    bankBuildModal.promptPlaceholders = data.placeholders || bankBuildModal.promptPlaceholders
    bankBuildModal.systemPrompt = data.system_prompt || bankBuildModal.systemPrompt
    bankBuildModal.userPromptTemplate = data.user_prompt_template || bankBuildModal.userPromptTemplate
    message.success('已保存为我的默认提示词')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存提示词配置失败')
  } finally {
    bankBuildModal.promptSaveLoading = false
  }
}

async function openPromptPreview() {
  if (!bankBuildModal.systemPrompt.trim() || !bankBuildModal.userPromptTemplate.trim()) {
    message.warning('请先填写系统提示词和用户提示词模板')
    return
  }

  const payload = buildPromptPreviewPayload()
  if (Object.keys(payload.type_distribution).length === 0) {
    message.warning('请至少设置一种题型的数量')
    return
  }

  bankBuildModal.promptPreviewLoading = true
  promptPreviewModal.visible = true
  try {
    const data: any = await request.post('/questions/generation/prompt-preview', payload)
    promptPreviewModal.items = data.rendered_user_prompts || []
    promptPreviewModal.note = data.preview_note || ''
    bankBuildModal.promptPlaceholders = data.placeholders || bankBuildModal.promptPlaceholders
    bankBuildModal.promptPreviewDirty = false
    bankBuildModal.promptSeed = data.prompt_seed
  } catch (e: any) {
    promptPreviewModal.visible = false
    message.error(e?.response?.data?.detail || '刷新提示词预览失败')
  } finally {
    bankBuildModal.promptPreviewLoading = false
  }
}

async function copyPromptPlaceholder(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    message.success(`已复制 ${text}`)
  } catch {
    message.error('复制失败')
  }
}

async function showBankBuildModal() {
  bankBuildModal.materialIds = []
  bankBuildModal.materialInfo = null
  bankBuildModal.selectionMode = 'stable'
  bankBuildModal.difficulty = 3
  bankBuildModal.bloomLevel = undefined
  bankBuildModal.maxUnits = 10
  bankBuildModal.customPrompt = ''
  bankBuildModal.systemPrompt = ''
  bankBuildModal.userPromptTemplate = ''
  bankBuildModal.promptConfigCollapsed = true
  bankBuildModal.hasSavedPromptConfig = false
  bankBuildModal.promptDefaults = { system_prompt: '', user_prompt_template: '' }
  bankBuildModal.promptPlaceholders = []
  clearPromptPreview(false)
  bankTypeDist.single_choice = 5
  bankTypeDist.multiple_choice = 2
  bankTypeDist.true_false = 3
  bankTypeDist.fill_blank = 0
  bankTypeDist.short_answer = 0
  bankBuildModal.visible = true

  // Fetch parsed + vectorized materials and model name
  bankBuildModal.materialsLoading = true
  try {
    const [d1, d2, healthData]: any[] = await Promise.all([
      request.get('/materials', { params: { status: 'parsed', skip: 0, limit: 100 } }),
      request.get('/materials', { params: { status: 'vectorized', skip: 0, limit: 100 } }),
      request.get('/health').catch(() => null),
    ])
    parsedMaterials.value = [...(d1.data || []), ...(d2.data || [])]
    if (healthData?.llm_model) {
      genModelName.value = healthData.llm_model
    }
  } catch {
    parsedMaterials.value = []
  } finally {
    bankBuildModal.materialsLoading = false
  }

  await loadPromptConfig()
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

watch(
  () => [
    bankBuildModal.visible,
    bankBuildModal.materialIds.join(','),
    bankBuildModal.selectionMode,
    bankBuildModal.difficulty,
    bankBuildModal.bloomLevel || '',
    bankBuildModal.maxUnits,
    bankBuildModal.customPrompt,
    bankBuildModal.systemPrompt,
    bankBuildModal.userPromptTemplate,
    bankTypeDist.single_choice,
    bankTypeDist.multiple_choice,
    bankTypeDist.true_false,
    bankTypeDist.fill_blank,
    bankTypeDist.short_answer,
  ],
  (_, previous) => {
    if (!bankBuildModal.visible || !previous) return
    const prevVisible = previous[0]
    if (!prevVisible) return
    bankBuildModal.promptPreviewDirty = true
    bankBuildModal.promptSeed = undefined
  },
)

async function autoSuggest() {
  bankBuildModal.suggestLoading = true
  try {
    if (bankBuildModal.materialIds.length > 0) {
      const suggestions = await fetchMaterialSuggestions(bankBuildModal.materialIds)
      const mergedDistribution = createEmptyTypeDistribution()
      let weightedDifficulty = 0
      let totalWeight = 0

      for (const suggestion of suggestions) {
        for (const questionType of QUESTION_TYPE_KEYS) {
          mergedDistribution[questionType] += suggestion.suggestedDistribution[questionType] || 0
        }
        weightedDifficulty += (suggestion.difficulty || 3) * suggestion.weight
        totalWeight += suggestion.weight
      }

      bankTypeDist.single_choice = mergedDistribution.single_choice || 0
      bankTypeDist.multiple_choice = mergedDistribution.multiple_choice || 0
      bankTypeDist.true_false = mergedDistribution.true_false || 0
      bankTypeDist.fill_blank = mergedDistribution.fill_blank || 0
      bankTypeDist.short_answer = mergedDistribution.short_answer || 0
      bankBuildModal.difficulty = totalWeight > 0 ? Math.round(weightedDifficulty / totalWeight) : 3
      message.success(`AI建议：基于 ${suggestions.length} 个素材，生成 ${sumTypeDistribution(mergedDistribution)} 道题目`)
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
  const dist = buildPositiveTypeDistribution()
  if (Object.keys(dist).length === 0) {
    message.warning('请至少设置一种题型的数量')
    return
  }
  if (!bankBuildModal.systemPrompt.trim() || !bankBuildModal.userPromptTemplate.trim()) {
    message.warning('请先填写系统提示词和用户提示词模板')
    return
  }

  bankBuildModal.loading = true
  startGenProgress(bankTotalCount.value)

  // Aggregated stats
  let allPreviewItems: any[] = []
  let aggTokens = { total: 0, prompt: 0, completion: 0 }
  let aggDuration = 0
  let modelName = ''
  let aggRequestedTotal = 0
  let aggGeneratedTotal = 0
  let aggFallbackCount = 0
  let aggNearDuplicateCount = 0
  let aggExistingNearDuplicateCount = 0
  let aggDifficultyMismatchCount = 0
  let aggBloomMismatchCount = 0
  let aggWarnings: string[] = []
  let aggQualityGateFailed = false
  let aggSelectedUnitCount = 0
  let aggConfiguredMaxUnits = bankBuildModal.maxUnits

  try {
    const payload = {
      difficulty: bankBuildModal.difficulty,
      bloom_level: bankBuildModal.bloomLevel || undefined,
      max_units: bankBuildModal.maxUnits,
      selection_mode: bankBuildModal.selectionMode,
      custom_prompt: bankBuildModal.customPrompt || undefined,
      system_prompt: bankBuildModal.systemPrompt.trim() || undefined,
      user_prompt_template: bankBuildModal.userPromptTemplate.trim() || undefined,
      prompt_seed: bankBuildModal.promptSeed,
    }

    if (bankBuildModal.materialIds.length > 0) {
      const suggestions = await fetchMaterialSuggestions(bankBuildModal.materialIds)
      const materialPlans = buildMaterialGenerationPlans(bankBuildModal.materialIds, dist, suggestions)
      if (materialPlans.length === 0) {
        throw new Error('未生成有效的素材分配计划')
      }

      for (const plan of materialPlans) {
        const result: any = await request.post(
          `/questions/preview/bank/${plan.materialId}`,
          {
            ...payload,
            type_distribution: plan.typeDistribution,
          },
          { timeout: 600000 },
        )
        allPreviewItems.push(...(result.questions || []))
        if (result.model_name) modelName = result.model_name
        if (result.stats) {
          aggTokens.total += result.stats.total_tokens || 0
          aggTokens.prompt += result.stats.prompt_tokens || 0
          aggTokens.completion += result.stats.completion_tokens || 0
          aggDuration += result.stats.duration_seconds || 0
          aggRequestedTotal += result.stats.requested_total || sumTypeDistribution(plan.typeDistribution)
          aggGeneratedTotal += result.stats.generated_total || (result.questions || []).length
          aggFallbackCount += result.stats.fallback_count || 0
          aggNearDuplicateCount += result.stats.near_duplicate_count || 0
          aggExistingNearDuplicateCount += result.stats.existing_near_duplicate_count || 0
          aggDifficultyMismatchCount += result.stats.difficulty_mismatch_count || 0
          aggBloomMismatchCount += result.stats.bloom_mismatch_count || 0
          aggSelectedUnitCount += result.stats.selected_unit_count || 0
          aggConfiguredMaxUnits = result.stats.configured_max_units || aggConfiguredMaxUnits
          aggWarnings.push(...((result.stats.warnings || []) as string[]).map(warning => `《${plan.materialTitle}》：${warning}`))
          aggQualityGateFailed = aggQualityGateFailed || !!result.stats.quality_gate_failed
        }
      }
    } else {
      // Free preview generation (no DB save)
      const result: any = await request.post(
        '/questions/preview/free',
        payload,
        { timeout: 600000 },
      )
      allPreviewItems = result.questions || []
      if (result.model_name) modelName = result.model_name
      if (result.stats) {
        aggTokens.total = result.stats.total_tokens || 0
        aggTokens.prompt = result.stats.prompt_tokens || 0
        aggTokens.completion = result.stats.completion_tokens || 0
        aggDuration = result.stats.duration_seconds || 0
        aggRequestedTotal = result.stats.requested_total || sumTypeDistribution(dist)
        aggGeneratedTotal = result.stats.generated_total || allPreviewItems.length
        aggFallbackCount = result.stats.fallback_count || 0
        aggNearDuplicateCount = result.stats.near_duplicate_count || 0
        aggExistingNearDuplicateCount = result.stats.existing_near_duplicate_count || 0
        aggDifficultyMismatchCount = result.stats.difficulty_mismatch_count || 0
        aggBloomMismatchCount = result.stats.bloom_mismatch_count || 0
        aggSelectedUnitCount = result.stats.selected_unit_count || 0
        aggConfiguredMaxUnits = result.stats.configured_max_units || aggConfiguredMaxUnits
        aggWarnings = [...(result.stats.warnings || [])]
        aggQualityGateFailed = !!result.stats.quality_gate_failed
      }
    }

    stopGenProgress(true)
    await new Promise(r => setTimeout(r, 600))
    bankBuildModal.visible = false

    // Open preview drawer for review
    previewUidCounter = 0
    previewQuestions.value = allPreviewItems.map(assignPreviewUid)
    previewSelectedKeys.value = []
    const dur = aggDuration || (Date.now() - genStartTime) / 1000
    previewStats.value = {
      modelName,
      durationText: formatDuration(dur * 1000),
      totalTokens: aggTokens.total,
      promptTokens: aggTokens.prompt,
      completionTokens: aggTokens.completion,
      requestedTotal: aggRequestedTotal || bankTotalCount.value,
      generatedTotal: aggGeneratedTotal || allPreviewItems.length,
      fallbackCount: aggFallbackCount,
      nearDuplicateCount: aggNearDuplicateCount,
      existingNearDuplicateCount: aggExistingNearDuplicateCount,
      difficultyMismatchCount: aggDifficultyMismatchCount,
      bloomMismatchCount: aggBloomMismatchCount,
      configuredMaxUnits: aggConfiguredMaxUnits,
      selectedUnitCount: aggSelectedUnitCount,
      warnings: Array.from(new Set(aggWarnings.filter(Boolean))),
      qualityGateFailed: aggQualityGateFailed,
    }
    previewDrawerVisible.value = true
    if (aggQualityGateFailed) {
      message.warning(`已生成 ${allPreviewItems.length} 道题目，当前预览包含质量风险，请审阅后决定是否保存`)
    } else {
      message.success(`已生成 ${allPreviewItems.length} 道题目，请审阅后保存`)
    }
  } catch {
    stopGenProgress(false)
    message.error('题目生成失败，请重试')
  } finally {
    bankBuildModal.loading = false
  }
}

function closeBankResult() {
  bankResultModal.visible = false
  fetchQuestions()
}

// ---- Preview & Review Functions ----
function removePreviewQuestion(uid: string) {
  previewQuestions.value = previewQuestions.value.filter(q => q._uid !== uid)
}

function removeSelectedPreview() {
  previewQuestions.value = previewQuestions.value.filter(
    q => !previewSelectedKeys.value.includes(q._uid)
  )
  message.success(`已移除 ${previewSelectedKeys.value.length} 道题目`)
  previewSelectedKeys.value = []
}

async function savePreviewQuestions() {
  if (previewQuestions.value.length === 0) {
    message.warning('没有可保存的题目')
    return
  }
  previewSaving.value = true
  try {
    // Strip frontend-only fields before sending
    const payload = previewQuestions.value.map(({ _uid, _fromExisting, ...rest }: any) => rest)
    const result: any = await request.post('/questions/batch/create-raw', {
      questions: payload,
    })
    message.success(`成功保存 ${result.generated} 道题目为草稿`)
    previewDrawerVisible.value = false
    previewQuestions.value = []
    fetchQuestions()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败，请重试')
  } finally {
    previewSaving.value = false
  }
}

function onPreviewDrawerClose() {
  if (previewQuestions.value.length === 0) {
    previewDrawerVisible.value = false
    return
  }
  if (previewQuestions.value.length > 0 && !previewSaving.value) {
    Modal.confirm({
      title: '确认放弃',
      content: `有 ${previewQuestions.value.length} 道题目未保存，确定放弃？`,
      okText: '放弃',
      okType: 'danger',
      cancelText: '继续编辑',
      onOk() {
        previewQuestions.value = []
        previewDrawerVisible.value = false
      },
      onCancel() {
        previewDrawerVisible.value = true
      },
    })
  }
}

function showPreviewDetail(record: any) {
  detailQuestion.value = {
    ...record,
    id: record._uid,
    status: 'draft',
    usage_count: 0,
    created_at: new Date().toISOString(),
  }
  aiCheckResult.value = record.quality_review || null
  reviewHistory.value = []
  detailVisible.value = true
}

// ---- Candidate Selector Functions ----
function openCandidateSelector() {
  candidateSelectedKeys.value = []
  candidateFilters.keyword = ''
  candidateFilters.question_type = undefined
  candidateFilters.dimension = undefined
  candidatePagination.current = 1
  candidateSelectorVisible.value = true
  fetchCandidateQuestions()
}

async function fetchCandidateQuestions() {
  candidateLoading.value = true
  try {
    const params: any = {
      skip: (candidatePagination.current - 1) * candidatePagination.pageSize,
      limit: candidatePagination.pageSize,
      status: 'approved',
    }
    if (candidateFilters.keyword) params.keyword = candidateFilters.keyword
    if (candidateFilters.question_type) params.question_type = candidateFilters.question_type
    if (candidateFilters.dimension) params.dimension = candidateFilters.dimension

    const data: any = await request.get('/questions', { params })
    candidateQuestions.value = data.items || []
    candidatePagination.total = data.total || 0
  } catch {
    candidateQuestions.value = []
  } finally {
    candidateLoading.value = false
  }
}

function handleCandidateTableChange(pag: any) {
  candidatePagination.current = pag.current
  candidatePagination.pageSize = pag.pageSize
  fetchCandidateQuestions()
}

function addCandidatesToPreview() {
  const selected = candidateQuestions.value.filter(
    (q: any) => candidateSelectedKeys.value.includes(q.id)
  )
  let addedCount = 0
  for (const q of selected) {
    // Check duplicates by stem
    const exists = previewQuestions.value.some((p: any) => p.stem === q.stem)
    if (exists) continue

    previewQuestions.value.push(assignPreviewUid({
      question_type: q.question_type,
      stem: q.stem,
      options: q.options,
      correct_answer: q.correct_answer,
      explanation: q.explanation,
      difficulty: q.difficulty,
      dimension: q.dimension,
      knowledge_tags: q.knowledge_tags,
      bloom_level: q.bloom_level,
      source_material_id: q.source_material_id,
      source_knowledge_unit_id: q.source_knowledge_unit_id,
      source_material_title: q.source_material_title,
      source_knowledge_unit_title: q.source_knowledge_unit_title,
      _fromExisting: true,
    }))
    addedCount++
  }
  if (addedCount > 0) {
    message.success(`已添加 ${addedCount} 道题目`)
  } else {
    message.info('没有新题目可添加（可能已存在）')
  }
  candidateSelectorVisible.value = false
}

// ---- Init ----
const route = useRoute()

onMounted(() => {
  if (route.query.tab === 'review') {
    activeTab.value = 'review'
    fetchReviewQuestions()
  } else {
    fetchQuestions()
  }
  fetchReviewCount()
})

onBeforeUnmount(() => {
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
.question-filter-actions {
  display: flex;
  justify-content: flex-end;
  min-height: 32px;
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
.stem-cell {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.5;
  max-height: 3em;
  word-break: break-all;
}

.source-cell {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #666;
}

.table-action-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  max-width: 100%;
}

.table-action-group :deep(.ant-btn-link) {
  padding-inline: 0;
  height: auto;
}

/* Generation progress - animated robot */
.gen-model-info {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 10px 16px;
  background: linear-gradient(135deg, #f0f7ff 0%, #e8f4f8 100%);
  border-radius: 8px;
  border: 1px solid #d6e8f5;
}
.gen-robot-icon {
  font-size: 28px;
  color: #1F4E79;
  animation: robotPulse 1.5s ease-in-out infinite;
}
.gen-model-name {
  font-size: 14px;
  font-weight: 600;
  color: #1F4E79;
}

@keyframes robotPulse {
  0%, 100% { transform: scale(1) rotate(0deg); opacity: 1; }
  25% { transform: scale(1.15) rotate(-5deg); opacity: 0.85; }
  50% { transform: scale(1) rotate(0deg); opacity: 1; }
  75% { transform: scale(1.15) rotate(5deg); opacity: 0.85; }
}

/* Generation result report */
.gen-report-section {
  margin-top: 16px;
}
.gen-report-title {
  font-size: 15px;
  font-weight: 600;
  color: #333;
  margin-bottom: 8px;
}
.gen-report-card {
  background: #fafafa;
  border-radius: 8px;
  padding: 12px 16px;
  border: 1px solid #f0f0f0;
}
.gen-report-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px solid #f0f0f0;
}
.gen-report-row:last-child {
  border-bottom: none;
}
.gen-report-label {
  color: #666;
  font-size: 13px;
}
.gen-report-value {
  font-weight: 600;
  color: #333;
  font-size: 13px;
}

/* Type distribution bars */
.gen-type-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid #f0f0f0;
}
.gen-type-row:last-child {
  border-bottom: none;
}
.gen-type-label {
  width: 56px;
  font-size: 13px;
  color: #666;
  flex-shrink: 0;
}
.gen-type-count {
  width: 44px;
  font-size: 13px;
  font-weight: 600;
  color: #333;
  flex-shrink: 0;
  text-align: right;
}
.gen-type-bar-bg {
  flex: 1;
  height: 12px;
  background: #f0f0f0;
  border-radius: 6px;
  overflow: hidden;
}
.gen-type-bar {
  height: 100%;
  background: linear-gradient(90deg, #1F4E79, #3D8ED0);
  border-radius: 6px;
  transition: width 0.6s ease;
}
.gen-type-pct {
  width: 36px;
  font-size: 12px;
  color: #999;
  flex-shrink: 0;
  text-align: right;
}
</style>
