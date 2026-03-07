<template>
  <div class="page-container">
    <div class="page-header">
      <h2>成绩管理</h2>
    </div>

    <!-- Leaderboard Card -->
    <a-card class="leaderboard-card" :bordered="false" v-if="!selectedScore && !reviewMode" style="margin-bottom: 20px;">
      <div class="leaderboard-header">
        <div class="leaderboard-title-row">
          <span class="leaderboard-title">🏆 英雄榜</span>
          <div class="leaderboard-actions">
            <span style="font-size: 13px; color: #666; margin-right: 8px;">参与排名</span>
            <a-switch
              :checked="showOnLeaderboard"
              :loading="optOutLoading"
              @change="toggleLeaderboard"
              size="small"
            />
          </div>
        </div>
      </div>
      <a-spin :spinning="leaderboardLoading">
        <div class="leaderboard-top3" v-if="leaderboardData.length > 0">
          <div
            v-for="(item, idx) in leaderboardData.slice(0, 3)"
            :key="item.user_id"
            class="top3-item"
            :class="{ 'top3-current': item.user_id === currentUserId }"
          >
            <div class="top3-medal">
              {{ idx === 0 ? '🥇' : idx === 1 ? '🥈' : '🥉' }}
            </div>
            <div class="top3-info">
              <div class="top3-name">{{ item.full_name || item.username }}</div>
              <div class="top3-score">
                得分率 <strong>{{ item.score_ratio }}%</strong>
                <a-tag :color="levelColor(item.level)" size="small" style="margin-left: 4px">{{ item.level }}</a-tag>
              </div>
              <div class="top3-exam">{{ item.exam_title }}</div>
            </div>
          </div>
        </div>
        <a-empty v-else description="暂无排名数据" :image="simpleImage" />
      </a-spin>
      <div class="leaderboard-footer" v-if="leaderboardData.length > 0">
        <a-button type="link" @click="leaderboardModalVisible = true">查看完整榜单 →</a-button>
      </div>
    </a-card>

    <!-- Leaderboard Modal -->
    <a-modal
      v-model:open="leaderboardModalVisible"
      title="🏆 英雄榜 — 前20名"
      :footer="null"
      width="720px"
    >
      <a-table
        :columns="leaderboardColumns"
        :data-source="leaderboardData"
        :pagination="false"
        row-key="user_id"
        size="middle"
        :row-class-name="(record: any) => record.user_id === currentUserId ? 'leaderboard-current-row' : ''"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'rank'">
            <span v-if="record.rank === 1" style="font-size: 18px;">🥇</span>
            <span v-else-if="record.rank === 2" style="font-size: 18px;">🥈</span>
            <span v-else-if="record.rank === 3" style="font-size: 18px;">🥉</span>
            <span v-else style="font-weight: 600; color: #666;">{{ record.rank }}</span>
          </template>
          <template v-if="column.key === 'name'">
            <span>{{ record.full_name || record.username }}</span>
            <a-tag v-if="record.user_id === currentUserId" color="blue" size="small" style="margin-left: 4px">我</a-tag>
          </template>
          <template v-if="column.key === 'score_ratio'">
            <strong :style="{ color: getScoreColor(record.score_ratio, 100) }">{{ record.score_ratio }}%</strong>
          </template>
          <template v-if="column.key === 'score'">
            {{ record.total_score }} / {{ record.max_score }}
          </template>
          <template v-if="column.key === 'level'">
            <a-tag :color="levelColor(record.level)">{{ record.level }}</a-tag>
          </template>
        </template>
      </a-table>
    </a-modal>

    <!-- Archived Scores (admin only) -->
    <a-card :bordered="false" v-if="isAdmin && archiveMode && !selectedScore && !reviewMode">
      <div style="display: flex; gap: 12px; margin-bottom: 16px; align-items: center;">
        <a-button @click="exitArchiveMode">
          <LeftOutlined /> 返回成绩管理
        </a-button>
        <span style="color: #999; font-size: 14px;">成绩存档 — 已删除的成绩记录</span>
      </div>
      <a-table
        :columns="archivedColumns"
        :data-source="archivedScores"
        :loading="archivedLoading"
        :pagination="archivedPagination"
        row-key="answer_sheet_id"
        @change="handleArchivedTableChange"
        size="middle"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'total_score'">
            <span :style="{ color: getScoreColor(record.total_score, record.max_score), fontWeight: 'bold' }">
              {{ record.total_score }}
            </span>
            <span style="color: #999"> / {{ record.max_score }}</span>
          </template>
          <template v-if="column.key === 'level'">
            <a-tag v-if="record.level" :color="levelColor(record.level)">{{ record.level }}</a-tag>
            <span v-else style="color: #999">-</span>
          </template>
          <template v-if="column.key === 'submit_time'">
            {{ record.submit_time ? new Date(record.submit_time).toLocaleString('zh-CN') : '-' }}
          </template>
          <template v-if="column.key === 'deleted_at'">
            {{ record.deleted_at ? new Date(record.deleted_at).toLocaleString('zh-CN') : '-' }}
          </template>
          <template v-if="column.key === 'actions'">
            <a-popconfirm title="确定恢复该成绩？" @confirm="restoreScore(record)">
              <a-button type="link" size="small">恢复</a-button>
            </a-popconfirm>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Manager Score List (admin/organizer) -->
    <a-card :bordered="false" v-if="isManager && !archiveMode && !selectedScore && !reviewMode">
      <div style="display: flex; gap: 12px; margin-bottom: 16px; align-items: center;">
        <a-input
          v-model:value="managerKeyword"
          placeholder="搜索用户名/姓名/考试名称"
          style="width: 280px"
          allow-clear
          @press-enter="fetchAllScores"
        >
          <template #prefix><SearchOutlined /></template>
        </a-input>
        <a-button type="primary" @click="handleExportScores" :loading="exporting">
          <ExportOutlined /> {{ managerSelectedKeys.length > 0 ? `导出选中 (${managerSelectedKeys.length})` : '导出选中列表' }}
        </a-button>
        <div style="flex: 1"></div>
        <a-button v-if="isAdmin" @click="enterArchiveMode">
          <DatabaseOutlined /> 存档成绩
        </a-button>
      </div>
      <a-table
        :columns="managerColumns"
        :data-source="allScores"
        :loading="allScoresLoading"
        :pagination="managerPagination"
        :row-selection="{ selectedRowKeys: managerSelectedKeys, onChange: onManagerSelectChange }"
        row-key="answer_sheet_id"
        @change="handleManagerTableChange"
        size="middle"
      >
        <template #customFilterDropdown="{ column, confirm, clearFilters }">
          <div style="padding: 8px">
            <a-input
              :placeholder="`搜索${column.title}`"
              :value="filterSearchValues[column.dataIndex as string]"
              @update:value="(val: string) => filterSearchValues[column.dataIndex as string] = val"
              style="width: 200px; margin-bottom: 8px; display: block"
              @press-enter="() => { handleColumnFilterConfirm(column.dataIndex as string); confirm() }"
            />
            <div style="display: flex; justify-content: space-between;">
              <a-button type="primary" size="small" @click="() => { handleColumnFilterConfirm(column.dataIndex as string); confirm() }">
                <SearchOutlined /> 搜索
              </a-button>
              <a-button size="small" @click="() => { handleColumnFilterReset(column.dataIndex as string); clearFilters && clearFilters() }">
                重置
              </a-button>
            </div>
          </div>
        </template>
        <template #customFilterIcon="{ column, filtered }">
          <SearchOutlined :style="{ color: filtered ? '#1890ff' : undefined }" />
        </template>
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'total_score'">
            <span :style="{ color: getScoreColor(record.total_score, record.max_score), fontWeight: 'bold' }">
              {{ record.total_score }}
            </span>
            <span style="color: #999"> / {{ record.max_score }}</span>
          </template>
          <template v-if="column.key === 'score_ratio'">
            <strong :style="{ color: getScoreColor(record.score_ratio, 100) }">{{ record.score_ratio }}%</strong>
          </template>
          <template v-if="column.key === 'level'">
            <a-tag v-if="record.level" :color="levelColor(record.level)">{{ record.level }}</a-tag>
            <span v-else style="color: #999">-</span>
          </template>
          <template v-if="column.key === 'submit_time'">
            {{ record.submit_time ? new Date(record.submit_time).toLocaleString('zh-CN') : '-' }}
          </template>
          <template v-if="column.key === 'actions'">
            <a-space>
              <a-button type="link" size="small" @click="viewDiagnosticByScoreId(record)">诊断报告</a-button>
              <a-button type="link" size="small" :disabled="!canDownloadCertForRecord(record)" @click="downloadCertForRecord(record)">下载证书</a-button>
              <a-popconfirm title="确定删除该成绩？删除后将进入存档。" @confirm="deleteScoreBySheet(record)">
                <a-button type="link" size="small" danger :disabled="record.user_id !== currentUserId">删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Personal Score List (examinee/reviewer) -->
    <a-card :bordered="false" v-if="!isManager && !selectedScore && !reviewMode">
      <a-table
        :columns="columns"
        :data-source="scores"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
        @change="handleTableChange"
        size="middle"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'total_score'">
            <template v-if="record.total_score != null">
              <span :style="{ color: getScoreColor(record.total_score, record.max_score), fontWeight: 'bold' }">
                {{ record.total_score }}
              </span>
              <span style="color: #999"> / {{ record.max_score }}</span>
            </template>
            <span v-else style="color: #999">-</span>
          </template>
          <template v-if="column.key === 'level'">
            <a-tag v-if="record.level" :color="levelColor(record.level)">{{ record.level }}</a-tag>
            <span v-else style="color: #999">-</span>
          </template>
          <template v-if="column.key === 'percentile_rank'">
            {{ record.percentile_rank != null ? `前${100 - record.percentile_rank}%` : '-' }}
          </template>
          <template v-if="column.key === 'status'">
            <a-tag v-if="record.status === 'scored'" color="green">已评分</a-tag>
            <a-tag v-else-if="record.status === 'submitted'" color="orange">评分中</a-tag>
            <a-tag v-else color="default">进行中</a-tag>
          </template>
          <template v-if="column.key === 'actions'">
            <a-space>
              <a-button type="link" size="small" :disabled="!record.score_id" @click="viewDiagnostic(record)">诊断分析报告</a-button>
              <a-button type="link" size="small" :disabled="!record.score_id" @click="startReview(record)">复盘</a-button>
              <a-button v-if="record.status === 'submitted' && !record.score_id" type="link" size="small" :loading="gradingId === record.id" @click="manualGrade(record)">手动评分</a-button>
              <a-popconfirm title="确定删除该成绩？删除后将进入存档。" @confirm="deleteScore(record)">
                <a-button type="link" size="small" danger :disabled="record.status !== 'scored'">删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Diagnostic Report -->
    <template v-if="selectedScore && diagnostic">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
        <a-button @click="selectedScore = null">
          <LeftOutlined /> 返回列表
        </a-button>
        <a-space>
          <a-button type="primary" :loading="downloading" @click="downloadReport">
            <DownloadOutlined /> 下载报告
          </a-button>
          <a-button :loading="downloadingCert" :disabled="!canDownloadCert" @click="downloadCert" :style="canDownloadCert ? { background: certLevel === '优秀' ? '#B8860B' : '#1F4E79', borderColor: certLevel === '优秀' ? '#B8860B' : '#1F4E79', color: '#fff' } : {}">
            <SafetyCertificateOutlined /> 下载证书
          </a-button>
        </a-space>
      </div>

      <div ref="reportRef">
      <h2 style="text-align: center; margin-bottom: 20px; font-size: 22px">
        {{ diagnosticUserName }} AI素养评测诊断分析报告
      </h2>
      <!-- Overview -->
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

      <!-- Radar Chart + Bar Chart -->
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

      <!-- Dimension Analysis -->
      <a-card title="维度分析" :bordered="false" style="margin-bottom: 16px">
        <a-row :gutter="16">
          <a-col :span="8" v-for="(item, index) in (diagnostic.radar_data || [])" :key="index">
            <a-card size="small" :bordered="true" style="margin-bottom: 12px">
              <template #title>
                <a-tag :color="levelColor(item.level)">{{ item.level }}</a-tag>
                {{ item.dimension }}
              </template>
              <div style="margin-bottom: 8px">
                <a-progress :percent="item.score" :stroke-color="getProgressColor(item.score)" size="small" />
              </div>
              <p style="color: #666; font-size: 13px; margin: 0">{{ item.description }}</p>
            </a-card>
          </a-col>
        </a-row>
      </a-card>

      <!-- Strengths & Weaknesses -->
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
            <a-list :data-source="diagnostic.weaknesses || []" size="small">
              <template #renderItem="{ item }">
                <a-list-item>
                  <a-tag color="orange">{{ item.dimension }}</a-tag>
                  <span>{{ item.comment }} ({{ item.score }}分)</span>
                </a-list-item>
              </template>
              <template #header v-if="!(diagnostic.weaknesses || []).length">
                <span style="color: #999">暂无数据</span>
              </template>
            </a-list>
          </a-card>
        </a-col>
      </a-row>

      <!-- Recommendations -->
      <a-card title="个性化学习建议" :bordered="false">
        <a-list :data-source="diagnostic.recommendations || []" size="small">
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
      </div>
    </template>

    <!-- Review Mode: Wrong Answer Review -->
    <template v-if="reviewMode && !trainingMode && !trainingSubmitted">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
        <a-button @click="exitReview">
          <LeftOutlined /> 返回列表
        </a-button>
        <a-button type="primary" @click="startTraining" :loading="trainingLoading"
                  :disabled="!reviewData || reviewData.wrong_items.length === 0">
          <ThunderboltOutlined /> 就薄弱环节进行训练
        </a-button>
      </div>

      <a-card title="错题复盘" :bordered="false">
        <a-alert v-if="!reviewData?.wrong_items?.length"
                 type="success" message="恭喜！本次测试全部答对，没有错题。" show-icon style="margin-bottom: 16px" />

        <div v-for="(item, idx) in (reviewData?.wrong_items || [])" :key="idx"
             style="margin-bottom: 24px; border-bottom: 1px solid #f0f0f0; padding-bottom: 16px">
          <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px">
            <span style="font-weight: 600; font-size: 15px">第 {{ idx + 1 }} 题</span>
            <a-tag>{{ typeLabel(item.question_type) }}</a-tag>
            <a-tag v-if="item.dimension" color="blue">{{ item.dimension }}</a-tag>
            <a-tag color="red">{{ item.earned_score }}/{{ item.max_score }}分</a-tag>
          </div>

          <div style="font-size: 15px; line-height: 1.8; margin-bottom: 12px">{{ item.stem }}</div>

          <div v-if="item.options" style="margin-bottom: 12px">
            <div v-for="(val, key) in item.options" :key="key"
                 :style="{
                   padding: '6px 12px',
                   borderRadius: '4px',
                   marginBottom: '4px',
                   background: isCorrectOption(key as string, item.correct_answer) ? '#f6ffed'
                     : isUserWrongOption(key as string, item.user_answer, item.correct_answer) ? '#fff2f0' : 'transparent',
                   border: isCorrectOption(key as string, item.correct_answer) ? '1px solid #b7eb8f'
                     : isUserWrongOption(key as string, item.user_answer, item.correct_answer) ? '1px solid #ffa39e' : '1px solid #f0f0f0',
                 }">
              {{ key }}. {{ val }}
              <a-tag v-if="isCorrectOption(key as string, item.correct_answer)" color="green" style="margin-left: 8px">正确答案</a-tag>
              <a-tag v-if="isUserWrongOption(key as string, item.user_answer, item.correct_answer)" color="red" style="margin-left: 8px">你的答案</a-tag>
            </div>
          </div>

          <div v-if="!item.options" style="margin-bottom: 12px">
            <div style="margin-bottom: 4px"><strong>你的答案：</strong>{{ item.user_answer || '(未作答)' }}</div>
            <div><strong>正确答案：</strong>{{ item.correct_answer }}</div>
          </div>

          <a-alert type="info" show-icon style="margin-top: 8px">
            <template #message>
              <strong>解析：</strong>{{ item.explanation || item.feedback || '暂无解析' }}
            </template>
          </a-alert>
        </div>
      </a-card>
    </template>

    <!-- Review Mode: Training (Answering Variant Questions) -->
    <template v-if="reviewMode && trainingMode && !trainingSubmitted">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
        <a-button @click="trainingMode = false">
          <LeftOutlined /> 返回错题
        </a-button>
        <span style="color: #666; font-size: 14px">训练第 {{ trainingRound }} 轮 — {{ trainingCurrentIndex + 1 }}/{{ trainingQuestions.length }}</span>
        <a-button type="primary" danger @click="submitTraining"
                  :disabled="Object.keys(trainingAnswers).length === 0">
          提交训练
        </a-button>
      </div>

      <a-card :bordered="false" v-if="currentTrainingQuestion">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 16px">
          <span style="font-weight: 600; font-size: 16px">第 {{ trainingCurrentIndex + 1 }} 题</span>
          <a-tag>{{ typeLabel(currentTrainingQuestion.question_type) }}</a-tag>
        </div>

        <div style="font-size: 15px; line-height: 1.8; margin-bottom: 20px">
          {{ currentTrainingQuestion.stem }}
        </div>

        <!-- Single Choice -->
        <div v-if="currentTrainingQuestion.question_type === 'single_choice'">
          <a-radio-group v-model:value="trainingAnswers[trainingCurrentIndex]" style="width: 100%">
            <div v-for="(val, key) in currentTrainingQuestion.options" :key="key" style="margin-bottom: 12px">
              <a-radio :value="key" style="font-size: 14px">{{ key }}. {{ val }}</a-radio>
            </div>
          </a-radio-group>
        </div>

        <!-- Multiple Choice -->
        <div v-if="currentTrainingQuestion.question_type === 'multiple_choice'">
          <a-checkbox-group :value="trainingMultiAnswers" @change="onTrainingMultiChange" style="width: 100%">
            <div v-for="(val, key) in currentTrainingQuestion.options" :key="key" style="margin-bottom: 12px">
              <a-checkbox :value="key" style="font-size: 14px">{{ key }}. {{ val }}</a-checkbox>
            </div>
          </a-checkbox-group>
        </div>

        <!-- True/False -->
        <div v-if="currentTrainingQuestion.question_type === 'true_false'">
          <a-radio-group v-model:value="trainingAnswers[trainingCurrentIndex]" style="width: 100%">
            <div style="margin-bottom: 12px"><a-radio value="A">A. 正确</a-radio></div>
            <div style="margin-bottom: 12px"><a-radio value="B">B. 错误</a-radio></div>
          </a-radio-group>
        </div>

        <div style="display: flex; gap: 12px; margin-top: 24px">
          <a-button :disabled="trainingCurrentIndex === 0" @click="trainingCurrentIndex--">上一题</a-button>
          <a-button type="primary" :disabled="trainingCurrentIndex >= trainingQuestions.length - 1" @click="trainingCurrentIndex++">下一题</a-button>
        </div>
      </a-card>
    </template>

    <!-- Review Mode: Training Results -->
    <template v-if="reviewMode && trainingSubmitted">
      <div style="margin-bottom: 16px">
        <h3 style="margin: 0">训练结果 — 第 {{ trainingRound }} 轮</h3>
      </div>

      <a-row :gutter="16" style="margin-bottom: 16px">
        <a-col :span="8">
          <a-card :bordered="false">
            <a-statistic title="正确率"
              :value="trainingQuestions.length > 0 ? (trainingCorrectCount / trainingQuestions.length * 100).toFixed(0) : 0"
              suffix="%" />
          </a-card>
        </a-col>
        <a-col :span="8">
          <a-card :bordered="false">
            <a-statistic title="正确/总题数" :value="trainingCorrectCount" :suffix="`/ ${trainingQuestions.length}`" />
          </a-card>
        </a-col>
        <a-col :span="8">
          <a-card :bordered="false">
            <a-statistic title="训练轮次" :value="trainingRound" suffix="轮" />
          </a-card>
        </a-col>
      </a-row>

      <a-card title="题目详情" :bordered="false" style="margin-bottom: 16px">
        <div v-for="(result, idx) in trainingResults" :key="idx"
             style="margin-bottom: 20px; border-bottom: 1px solid #f0f0f0; padding-bottom: 16px">
          <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px">
            <span style="font-weight: 600">第 {{ idx + 1 }} 题</span>
            <a-tag :color="result.is_correct ? 'green' : 'red'">{{ result.is_correct ? '正确' : '错误' }}</a-tag>
            <a-tag>{{ typeLabel(result.question.question_type) }}</a-tag>
          </div>
          <div style="font-size: 14px; line-height: 1.8; margin-bottom: 8px">{{ result.question.stem }}</div>
          <div v-if="result.question.options" style="margin-bottom: 8px">
            <div v-for="(val, key) in result.question.options" :key="key"
                 :style="{
                   padding: '4px 8px', borderRadius: '4px', marginBottom: '2px',
                   background: isCorrectOption(key as string, result.correct_answer) ? '#f6ffed'
                     : isUserWrongOption(key as string, result.user_answer, result.correct_answer) ? '#fff2f0' : 'transparent',
                 }">
              {{ key }}. {{ val }}
              <a-tag v-if="isCorrectOption(key as string, result.correct_answer)" color="green" style="margin-left: 8px" size="small">正确答案</a-tag>
              <a-tag v-if="isUserWrongOption(key as string, result.user_answer, result.correct_answer)" color="red" style="margin-left: 8px" size="small">你的答案</a-tag>
            </div>
          </div>
          <a-alert v-if="result.explanation" type="info" show-icon style="margin-top: 8px">
            <template #message>
              <strong>解析：</strong>{{ result.explanation }}
            </template>
          </a-alert>
        </div>
      </a-card>

      <div style="display: flex; gap: 12px; justify-content: center">
        <a-button type="primary" size="large" @click="continueTraining" :loading="trainingLoading">
          <ThunderboltOutlined /> 继续训练
        </a-button>
        <a-button size="large" @click="exitReview">结束</a-button>
        <a-button size="large" @click="goRetakeExam">返回重新测试</a-button>
      </div>
    </template>

    <!-- Hidden Certificate Template -->
    <div ref="certRef" class="cert-container" :class="{ 'cert-excellent': certLevel === '优秀' }">
      <div class="cert-border">
        <div class="cert-inner">
          <!-- Corner decorations for excellent -->
          <template v-if="certLevel === '优秀'">
            <div class="cert-corner cert-corner-tl"></div>
            <div class="cert-corner cert-corner-tr"></div>
            <div class="cert-corner cert-corner-bl"></div>
            <div class="cert-corner cert-corner-br"></div>
          </template>
          <div class="cert-header">
            <div class="cert-icon">&#9733;</div>
            <h1 class="cert-title">AI素养评测证书</h1>
            <div class="cert-subtitle">CERTIFICATE OF AI LITERACY</div>
          </div>
          <div class="cert-divider"></div>
          <div class="cert-body">
            <p class="cert-name">{{ certNameOverride || userStore.userInfo?.full_name || userStore.userInfo?.username || '用户' }}</p>
            <p class="cert-text">
              AI素养评测成绩<span class="cert-level">{{ certLevel }}</span>，特发此证，以资鼓励。
            </p>
          </div>
          <div class="cert-footer">
            <div class="cert-org">社会科学智能实验室</div>
            <div class="cert-date">{{ certDate }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, nextTick, watch } from 'vue'
import { LeftOutlined, DownloadOutlined, SafetyCertificateOutlined, ThunderboltOutlined, SearchOutlined, ExportOutlined, FilterOutlined, DatabaseOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { useRouter } from 'vue-router'
import { message, Empty } from 'ant-design-vue'
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
import request from '@/utils/request'
import { useUserStore } from '@/stores/user'
import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'

echarts.use([
  RadarChart, BarChart, TitleComponent, TooltipComponent,
  LegendComponent, RadarComponent, GridComponent, CanvasRenderer,
])

const userStore = useUserStore()
const router = useRouter()

const simpleImage = Empty.PRESENTED_IMAGE_SIMPLE

const loading = ref(false)
const scores = ref<any[]>([])
const selectedScore = ref<any>(null)
const diagnostic = ref<any>(null)
const radarChartRef = ref<HTMLElement | null>(null)
const barChartRef = ref<HTMLElement | null>(null)
const reportRef = ref<HTMLElement | null>(null)
const certRef = ref<HTMLElement | null>(null)
const downloading = ref(false)
const downloadingCert = ref(false)

// Leaderboard state
const leaderboardData = ref<any[]>([])
const leaderboardLoading = ref(false)
const leaderboardModalVisible = ref(false)
const showOnLeaderboard = ref(true)
const optOutLoading = ref(false)
const currentUserId = computed(() => userStore.userInfo?.id ? String(userStore.userInfo.id) : '')

// Review/Training state
const reviewMode = ref(false)
const reviewData = ref<any>(null)
const reviewLoading = ref(false)
const trainingMode = ref(false)
const trainingQuestions = ref<any[]>([])
const trainingAnswers = reactive<Record<number, string>>({})
const trainingCurrentIndex = ref(0)
const trainingSubmitted = ref(false)
const trainingResults = ref<any[]>([])
const trainingLoading = ref(false)
const trainingRound = ref(0)
const trainingMultiAnswers = ref<string[]>([])

const currentTrainingQuestion = computed(() =>
  trainingQuestions.value[trainingCurrentIndex.value] || null
)
const trainingCorrectCount = computed(() =>
  trainingResults.value.filter(r => r.is_correct).length
)

const canDownloadCert = computed(() => {
  const level = diagnostic.value?.level
  return ['优秀', '良好', '合格'].includes(level)
})

// Overrides for downloading cert on behalf of other users (manager view)
const certNameOverride = ref('')
const certLevelOverride = ref('')

const certLevel = computed(() => {
  if (certLevelOverride.value) return certLevelOverride.value
  const level = diagnostic.value?.level
  return level === '优秀' ? '优秀' : '合格'
})

const diagnosticUserName = computed(() => {
  // If viewing another user's score from manager view
  if (isManager.value && selectedScore.value?.full_name) {
    return selectedScore.value.full_name || selectedScore.value.username || '用户'
  }
  return userStore.userInfo?.full_name || userStore.userInfo?.username || '用户'
})

const certDate = computed(() => {
  const now = new Date()
  return `${now.getFullYear()}年${now.getMonth() + 1}月`
})

let radarChart: echarts.ECharts | null = null
let barChart: echarts.ECharts | null = null

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条`,
})

const gradingId = ref<string | null>(null)

// --- Manager (admin/organizer) view ---
const userRole = computed(() => userStore.userInfo?.role || '')
const isManager = computed(() => ['admin', 'organizer'].includes(userRole.value))

const allScores = ref<any[]>([])
const allScoresLoading = ref(false)
const managerKeyword = ref('')
const managerSelectedKeys = ref<string[]>([])
const managerSelectedRows = ref<any[]>([])
const exporting = ref(false)

// Per-column filter state
const managerFilters = reactive<Record<string, string>>({
  username: '',
  full_name: '',
  exam_title: '',
  level: '',
})
// Temp search values for custom filter dropdowns
const filterSearchValues = reactive<Record<string, string>>({
  username: '',
  full_name: '',
  exam_title: '',
})
// Sort state
const managerSorter = reactive<{ field: string; order: string | null }>({
  field: '',
  order: null,
})

// Archive mode (admin only)
const isAdmin = computed(() => userRole.value === 'admin')
const archiveMode = ref(false)
const archivedScores = ref<any[]>([])
const archivedLoading = ref(false)
const archivedPagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条`,
})
const archivedColumns = [
  { title: '用户名', dataIndex: 'username', key: 'username', width: 120 },
  { title: '姓名', dataIndex: 'full_name', key: 'full_name', width: 120 },
  { title: '考试名称', dataIndex: 'exam_title', key: 'exam_title', ellipsis: true },
  { title: '得分', key: 'total_score', width: 120 },
  { title: '等级', key: 'level', width: 100 },
  { title: '提交时间', key: 'submit_time', width: 180 },
  { title: '删除时间', key: 'deleted_at', width: 180 },
  { title: '操作', key: 'actions', width: 100, fixed: 'right' as const },
]

const managerPagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条`,
})

const managerColumns = computed(() => [
  {
    title: '用户名', dataIndex: 'username', key: 'username', width: 120,
    customFilterDropdown: true,
    filteredValue: managerFilters.username ? [managerFilters.username] : [],
  },
  {
    title: '姓名', dataIndex: 'full_name', key: 'full_name', width: 120,
    customFilterDropdown: true,
    filteredValue: managerFilters.full_name ? [managerFilters.full_name] : [],
  },
  {
    title: '考试名称', dataIndex: 'exam_title', key: 'exam_title', ellipsis: true,
    customFilterDropdown: true,
    filteredValue: managerFilters.exam_title ? [managerFilters.exam_title] : [],
  },
  { title: '得分', key: 'total_score', width: 120, sorter: true, sortOrder: managerSorter.field === 'total_score' ? managerSorter.order : null },
  { title: '得分率', key: 'score_ratio', width: 90, align: 'center' as const, sorter: true, sortOrder: managerSorter.field === 'score_ratio' ? managerSorter.order : null },
  {
    title: '等级', key: 'level', width: 100,
    filters: [
      { text: '优秀', value: '优秀' },
      { text: '良好', value: '良好' },
      { text: '合格', value: '合格' },
      { text: '不合格', value: '不合格' },
    ],
    filteredValue: managerFilters.level ? managerFilters.level.split(',') : [],
  },
  { title: '提交时间', key: 'submit_time', width: 180, sorter: true, sortOrder: managerSorter.field === 'submit_time' ? managerSorter.order : null },
  { title: '操作', key: 'actions', width: 180, fixed: 'right' as const },
])

const columns = [
  { title: '考试', key: 'exam_title', dataIndex: 'exam_title', ellipsis: true },
  { title: '得分', key: 'total_score', width: 120 },
  { title: '等级', key: 'level', dataIndex: 'level', width: 90 },
  { title: '百分位', key: 'percentile_rank', width: 100 },
  { title: '状态', key: 'status', width: 100 },
  { title: '提交时间', key: 'submit_time', dataIndex: 'submit_time', width: 180 },
  { title: '操作', key: 'actions', width: 320, fixed: 'right' as const },
]

const leaderboardColumns = [
  { title: '排名', key: 'rank', dataIndex: 'rank', width: 70, align: 'center' as const },
  { title: '姓名', key: 'name', width: 150 },
  { title: '得分率', key: 'score_ratio', width: 100, align: 'center' as const },
  { title: '得分', key: 'score', width: 120, align: 'center' as const },
  { title: '等级', key: 'level', width: 90, align: 'center' as const },
  { title: '考试', key: 'exam_title', dataIndex: 'exam_title', ellipsis: true },
]

function levelColor(level: string): string {
  const map: Record<string, string> = {
    '优秀': 'green', '良好': 'blue', '合格': 'orange', '不合格': 'red', '需提升': 'red',
  }
  return map[level] || 'default'
}

function getScoreColor(score: number, max: number): string {
  const ratio = score / max
  if (ratio >= 0.9) return '#52c41a'
  if (ratio >= 0.8) return '#1890ff'
  if (ratio >= 0.6) return '#faad14'
  return '#f5222d'
}

function getProgressColor(score: number): string {
  if (score >= 90) return '#52c41a'
  if (score >= 80) return '#1890ff'
  if (score >= 60) return '#faad14'
  return '#f5222d'
}

// --- Leaderboard functions ---
async function fetchLeaderboard() {
  leaderboardLoading.value = true
  try {
    const data: any = await request.get('/scores/leaderboard', { params: { limit: 20 } })
    leaderboardData.value = data.items || []
  } catch (e) {
    leaderboardData.value = []
  } finally {
    leaderboardLoading.value = false
  }
}

async function loadLeaderboardStatus() {
  try {
    const me: any = await request.get('/users/me')
    showOnLeaderboard.value = me.show_on_leaderboard !== false
  } catch { /* ignore */ }
}

async function toggleLeaderboard() {
  optOutLoading.value = true
  try {
    const resp: any = await request.post('/scores/leaderboard/opt-out')
    showOnLeaderboard.value = resp.show_on_leaderboard
    message.success(resp.show_on_leaderboard ? '已加入英雄榜' : '已退出英雄榜')
    await fetchLeaderboard()
  } catch {
    message.error('操作失败，请重试')
  } finally {
    optOutLoading.value = false
  }
}

async function fetchScores() {
  loading.value = true
  try {
    const data: any = await request.get('/sessions')
    const all = Array.isArray(data) ? data : []
    // Only show submitted or scored sessions
    scores.value = all.filter((s: any) => s.status !== 'in_progress')
    pagination.total = scores.value.length
  } catch (e) {
    scores.value = []
  } finally {
    loading.value = false
  }
}

function handleTableChange(pag: any) {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
}

// --- Manager view functions ---
async function fetchAllScores() {
  allScoresLoading.value = true
  try {
    const params: any = {
      skip: (managerPagination.current - 1) * managerPagination.pageSize,
      limit: managerPagination.pageSize,
    }
    if (managerKeyword.value) params.keyword = managerKeyword.value
    // Per-column filters
    if (managerFilters.username) params.username = managerFilters.username
    if (managerFilters.full_name) params.full_name = managerFilters.full_name
    if (managerFilters.exam_title) params.exam_title = managerFilters.exam_title
    if (managerFilters.level) params.level = managerFilters.level
    if (managerSorter.field && managerSorter.order) {
      params.sort_field = managerSorter.field
      params.sort_order = managerSorter.order
    }
    const data: any = await request.get('/scores/all', { params })
    allScores.value = data.items || []
    managerPagination.total = data.total || 0
  } catch (e) {
    allScores.value = []
  } finally {
    allScoresLoading.value = false
  }
}

function handleManagerTableChange(pag: any, filters: any, sorter: any) {
  managerPagination.current = pag.current
  managerPagination.pageSize = pag.pageSize
  // Sync level filter from built-in dropdown
  if (filters?.level) {
    managerFilters.level = filters.level.join(',')
  } else {
    managerFilters.level = ''
  }
  // Sync sorter
  if (sorter?.order) {
    managerSorter.field = sorter.columnKey || sorter.field || ''
    managerSorter.order = sorter.order
  } else {
    managerSorter.field = ''
    managerSorter.order = null
  }
  fetchAllScores()
}

function handleColumnFilterConfirm(dataIndex: string) {
  managerFilters[dataIndex] = filterSearchValues[dataIndex] || ''
  managerPagination.current = 1
  fetchAllScores()
}

function handleColumnFilterReset(dataIndex: string) {
  filterSearchValues[dataIndex] = ''
  managerFilters[dataIndex] = ''
  managerPagination.current = 1
  fetchAllScores()
}

function onManagerSelectChange(keys: string[], rows: any[]) {
  managerSelectedKeys.value = keys
  managerSelectedRows.value = rows
}

async function handleExportScores() {
  exporting.value = true
  try {
    // Collect unique user_ids from selected rows
    const userIds = managerSelectedRows.value.length > 0
      ? [...new Set(managerSelectedRows.value.map(r => r.user_id))]
      : []
    const resp = await request.post('/scores/export', { user_ids: userIds }, {
      responseType: 'blob',
    })
    const blob = new Blob([resp as any], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `成绩导出_${new Date().toLocaleDateString('zh-CN').replace(/\//g, '-')}.xlsx`
    link.click()
    URL.revokeObjectURL(url)
    message.success('导出成功')
  } catch (e) {
    message.error('导出失败，请重试')
  } finally {
    exporting.value = false
  }
}

// --- Delete / Archive functions ---
async function deleteScore(record: any) {
  try {
    await request.delete(`/scores/${record.id}`)
    message.success('成绩已删除')
    await fetchScores()
  } catch (e: any) {
    message.error(e?.message || '删除失败')
  }
}

async function deleteScoreBySheet(record: any) {
  try {
    await request.delete(`/scores/${record.answer_sheet_id}`)
    message.success('成绩已删除')
    await fetchAllScores()
  } catch (e: any) {
    message.error(e?.message || '删除失败')
  }
}

function enterArchiveMode() {
  archiveMode.value = true
  fetchArchivedScores()
}

function exitArchiveMode() {
  archiveMode.value = false
  fetchAllScores()
}

async function fetchArchivedScores() {
  archivedLoading.value = true
  try {
    const params: any = {
      skip: (archivedPagination.current - 1) * archivedPagination.pageSize,
      limit: archivedPagination.pageSize,
    }
    const data: any = await request.get('/scores/archived', { params })
    archivedScores.value = data.items || []
    archivedPagination.total = data.total || 0
  } catch (e) {
    archivedScores.value = []
  } finally {
    archivedLoading.value = false
  }
}

function handleArchivedTableChange(pag: any) {
  archivedPagination.current = pag.current
  archivedPagination.pageSize = pag.pageSize
  fetchArchivedScores()
}

async function restoreScore(record: any) {
  try {
    await request.post(`/scores/${record.answer_sheet_id}/restore`)
    message.success('成绩已恢复')
    await fetchArchivedScores()
  } catch (e: any) {
    message.error(e?.message || '恢复失败')
  }
}

async function viewDiagnosticByScoreId(record: any) {
  selectedScore.value = record
  try {
    diagnostic.value = await request.get(`/scores/${record.score_id}/diagnostic`)
    await nextTick()
    renderRadarChart()
    renderBarChart()
  } catch (e) {
    message.error('获取诊断分析报告失败')
  }
}

function canDownloadCertForRecord(record: any): boolean {
  return ['优秀', '良好', '合格'].includes(record.level)
}

async function downloadCertForRecord(record: any) {
  if (!certRef.value || !canDownloadCertForRecord(record)) return
  downloadingCert.value = true
  try {
    // Temporarily update cert content for this user
    const origCertName = certNameOverride.value
    certNameOverride.value = record.full_name || record.username || '用户'
    const origCertLevelVal = certLevelOverride.value
    certLevelOverride.value = record.level === '优秀' ? '优秀' : '合格'

    await nextTick()

    certRef.value.style.left = '0'
    certRef.value.style.top = '0'
    certRef.value.style.opacity = '1'
    await nextTick()

    const canvas = await html2canvas(certRef.value, {
      scale: 2,
      useCORS: true,
      backgroundColor: null,
      width: 800,
      height: 566,
    })

    certRef.value.style.left = '-9999px'
    certRef.value.style.opacity = '0'

    const imgData = canvas.toDataURL('image/png')
    const pdf = new jsPDF('l', 'mm', 'a4')
    pdf.addImage(imgData, 'PNG', 0, 0, 297, 210)

    const displayName = record.full_name || record.username || '用户'
    pdf.save(`${displayName}AI素养评测证书.pdf`)
    message.success('证书下载成功')

    // Restore
    certNameOverride.value = origCertName
    certLevelOverride.value = origCertLevelVal
  } catch (e) {
    message.error('证书下载失败，请重试')
  } finally {
    if (certRef.value) {
      certRef.value.style.left = '-9999px'
      certRef.value.style.opacity = '0'
    }
    downloadingCert.value = false
  }
}

async function viewDiagnostic(record: any) {
  if (!record.score_id) {
    message.warning('该考试尚未评分，无法查看诊断分析报告')
    return
  }
  selectedScore.value = record
  try {
    diagnostic.value = await request.get(`/scores/${record.score_id}/diagnostic`)
    await nextTick()
    renderRadarChart()
    renderBarChart()
  } catch (e) {
    message.error('获取诊断分析报告失败')
  }
}

async function manualGrade(record: any) {
  gradingId.value = record.id
  try {
    await request.post(`/scores/grade/${record.id}`)
    message.success('评分完成')
    await fetchScores()
  } catch (e: any) {
    message.error(e?.message || '评分失败')
  } finally {
    gradingId.value = null
  }
}

function renderRadarChart() {
  if (!radarChartRef.value || !diagnostic.value?.radar_data) return

  if (radarChart) radarChart.dispose()
  radarChart = echarts.init(radarChartRef.value)

  const radarData = diagnostic.value.radar_data
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
  if (!barChartRef.value || !diagnostic.value?.comparison) return

  if (barChart) barChart.dispose()
  barChart = echarts.init(barChartRef.value)

  const items = diagnostic.value.comparison.items || []
  const dims = items.map((i: any) => i.dimension)
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

async function downloadReport() {
  if (!reportRef.value) return
  downloading.value = true
  try {
    const canvas = await html2canvas(reportRef.value, {
      scale: 2,
      useCORS: true,
      backgroundColor: '#f0f2f5',
    })
    const imgData = canvas.toDataURL('image/png')
    const imgWidth = 190 // A4 width minus margins (210 - 10*2)
    const imgHeight = (canvas.height * imgWidth) / canvas.width
    const pageHeight = 277 // A4 height minus margins (297 - 10*2)

    const pdf = new jsPDF('p', 'mm', 'a4')
    let heightLeft = imgHeight
    let position = 10 // top margin

    pdf.addImage(imgData, 'PNG', 10, position, imgWidth, imgHeight)
    heightLeft -= pageHeight

    while (heightLeft > 0) {
      position = position - pageHeight
      pdf.addPage()
      pdf.addImage(imgData, 'PNG', 10, position, imgWidth, imgHeight)
      heightLeft -= pageHeight
    }

    const displayName = userStore.userInfo?.full_name || userStore.userInfo?.username || '用户'
    pdf.save(`${displayName}AI素养分析报告.pdf`)
    message.success('报告下载成功')
  } catch (e) {
    message.error('报告下载失败，请重试')
  } finally {
    downloading.value = false
  }
}

async function downloadCert() {
  if (!certRef.value || !canDownloadCert.value) return
  downloadingCert.value = true
  try {
    // Temporarily show the certificate for rendering
    certRef.value.style.left = '0'
    certRef.value.style.top = '0'
    certRef.value.style.opacity = '1'
    await nextTick()

    const canvas = await html2canvas(certRef.value, {
      scale: 2,
      useCORS: true,
      backgroundColor: null,
      width: 800,
      height: 566,
    })

    // Hide again
    certRef.value.style.left = '-9999px'
    certRef.value.style.opacity = '0'

    const imgData = canvas.toDataURL('image/png')
    const pdf = new jsPDF('l', 'mm', 'a4') // landscape
    pdf.addImage(imgData, 'PNG', 0, 0, 297, 210)

    const displayName = userStore.userInfo?.full_name || userStore.userInfo?.username || '用户'
    pdf.save(`${displayName}AI素养评测证书.pdf`)
    message.success('证书下载成功')
  } catch (e) {
    message.error('证书下载失败，请重试')
  } finally {
    if (certRef.value) {
      certRef.value.style.left = '-9999px'
      certRef.value.style.opacity = '0'
    }
    downloadingCert.value = false
  }
}

// --- Review / Training functions ---

function typeLabel(t: string): string {
  const map: Record<string, string> = {
    single_choice: '单选题', multiple_choice: '多选题',
    true_false: '判断题', fill_blank: '填空题', short_answer: '简答题',
  }
  return map[t] || t
}

function isCorrectOption(key: string, correctAnswer: string): boolean {
  return correctAnswer?.toUpperCase().includes(key.toUpperCase()) || false
}

function isUserWrongOption(key: string, userAnswer: string, correctAnswer: string): boolean {
  if (!userAnswer) return false
  const isUserChoice = userAnswer.toUpperCase().includes(key.toUpperCase())
  const isCorrect = correctAnswer?.toUpperCase().includes(key.toUpperCase())
  return isUserChoice && !isCorrect
}

async function startReview(record: any) {
  if (!record.score_id) return
  reviewLoading.value = true
  reviewMode.value = true
  trainingMode.value = false
  trainingSubmitted.value = false
  try {
    reviewData.value = await request.get(`/scores/${record.score_id}/review`)
    selectedScore.value = record
  } catch (e) {
    message.error('获取复盘数据失败')
    reviewMode.value = false
  } finally {
    reviewLoading.value = false
  }
}

function exitReview() {
  reviewMode.value = false
  trainingMode.value = false
  trainingSubmitted.value = false
  reviewData.value = null
  selectedScore.value = null
  trainingQuestions.value = []
  trainingResults.value = []
  trainingRound.value = 0
  trainingCurrentIndex.value = 0
  trainingMultiAnswers.value = []
  Object.keys(trainingAnswers).forEach(k => delete trainingAnswers[k as any])
}

async function startTraining() {
  if (!reviewData.value?.wrong_items?.length) return
  trainingLoading.value = true
  try {
    const resp: any = await request.post('/scores/training/generate', {
      wrong_questions: reviewData.value.wrong_items,
      count: 5,
      difficulty: 3,
    }, { timeout: 120000 })
    trainingQuestions.value = resp.questions || []
    trainingMode.value = true
    trainingSubmitted.value = false
    trainingCurrentIndex.value = 0
    trainingRound.value += 1
    trainingMultiAnswers.value = []
    Object.keys(trainingAnswers).forEach(k => delete trainingAnswers[k as any])
  } catch (e) {
    message.error('生成训练题目失败，请重试')
  } finally {
    trainingLoading.value = false
  }
}

function onTrainingMultiChange(vals: any) {
  const sorted = [...vals].sort()
  trainingAnswers[trainingCurrentIndex.value] = sorted.join('')
  trainingMultiAnswers.value = sorted
}

function submitTraining() {
  const results: any[] = []
  trainingQuestions.value.forEach((q, idx) => {
    const userAns = (trainingAnswers[idx] || '').trim().toUpperCase()
    const correctAns = (q.correct_answer || '').trim().toUpperCase()

    let isCorrect = false
    if (q.question_type === 'multiple_choice') {
      const userSet = new Set(userAns.split(''))
      const correctSet = new Set(correctAns.split(''))
      isCorrect = userSet.size === correctSet.size && [...userSet].every(c => correctSet.has(c))
    } else {
      isCorrect = userAns === correctAns
    }

    results.push({
      question: q,
      user_answer: trainingAnswers[idx] || '',
      correct_answer: q.correct_answer,
      is_correct: isCorrect,
      explanation: q.explanation,
    })
  })

  trainingResults.value = results
  trainingSubmitted.value = true
  trainingMode.value = false
}

async function continueTraining() {
  trainingSubmitted.value = false
  await startTraining()
}

function goRetakeExam() {
  exitReview()
  router.push('/take-exam')
}

// Sync multi-choice UI when navigating training questions
watch(trainingCurrentIndex, () => {
  if (currentTrainingQuestion.value?.question_type === 'multiple_choice') {
    const current = trainingAnswers[trainingCurrentIndex.value] || ''
    trainingMultiAnswers.value = current ? current.split('') : []
  }
})

onMounted(() => {
  if (isManager.value) {
    fetchAllScores()
  } else {
    fetchScores()
  }
  fetchLeaderboard()
  loadLeaderboardStatus()
})

// Clean up charts on unmount
watch(selectedScore, (val) => {
  if (!val) {
    if (radarChart) { radarChart.dispose(); radarChart = null }
    if (barChart) { barChart.dispose(); barChart = null }
  }
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

/* Leaderboard Styles */
.leaderboard-card {
  background: linear-gradient(135deg, #fff9e6 0%, #fff3cd 50%, #ffeeba 100%);
  border: 1px solid #ffd700;
}
.leaderboard-header {
  margin-bottom: 16px;
}
.leaderboard-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.leaderboard-title {
  font-size: 20px;
  font-weight: 700;
  color: #8B6914;
}
.leaderboard-actions {
  display: flex;
  align-items: center;
}
.leaderboard-top3 {
  display: flex;
  gap: 16px;
  justify-content: center;
}
.top3-item {
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 12px;
  padding: 16px 20px;
  flex: 1;
  max-width: 280px;
  transition: transform 0.2s;
}
.top3-item:hover {
  transform: translateY(-2px);
}
.top3-current {
  border: 2px solid #1890ff;
  background: rgba(24, 144, 255, 0.08);
}
.top3-medal {
  font-size: 32px;
  line-height: 1;
}
.top3-info {
  flex: 1;
  min-width: 0;
}
.top3-name {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.top3-score {
  font-size: 13px;
  color: #666;
  margin-top: 4px;
}
.top3-exam {
  font-size: 12px;
  color: #999;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.leaderboard-footer {
  text-align: center;
  margin-top: 12px;
}
:deep(.leaderboard-current-row) {
  background-color: #e6f7ff !important;
}

/* Certificate Styles */
.cert-container {
  position: fixed;
  left: -9999px;
  top: 0;
  opacity: 0;
  width: 800px;
  height: 566px;
  background: linear-gradient(135deg, #f8f9fc 0%, #e8ecf4 50%, #f0f3f8 100%);
  font-family: 'SimSun', 'STSong', 'Songti SC', serif;
  z-index: -1;
}
.cert-excellent {
  background: linear-gradient(135deg, #fdf8ef 0%, #f5e6c8 50%, #faf0da 100%);
}

.cert-border {
  margin: 16px;
  height: calc(100% - 32px);
  border: 3px solid #1F4E79;
  padding: 4px;
}
.cert-excellent .cert-border {
  border-color: #B8860B;
}

.cert-inner {
  border: 1px solid #1F4E79;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 30px 60px;
  position: relative;
  overflow: hidden;
}
.cert-excellent .cert-inner {
  border-color: #B8860B;
}

/* Corner decorations */
.cert-corner {
  position: absolute;
  width: 60px;
  height: 60px;
  border: 2px solid #B8860B;
}
.cert-corner-tl { top: 8px; left: 8px; border-right: none; border-bottom: none; }
.cert-corner-tr { top: 8px; right: 8px; border-left: none; border-bottom: none; }
.cert-corner-bl { bottom: 8px; left: 8px; border-right: none; border-top: none; }
.cert-corner-br { bottom: 8px; right: 8px; border-left: none; border-top: none; }

.cert-header {
  text-align: center;
  margin-bottom: 8px;
}
.cert-icon {
  font-size: 36px;
  color: #1F4E79;
  margin-bottom: 4px;
}
.cert-excellent .cert-icon {
  color: #B8860B;
}
.cert-title {
  font-size: 32px;
  font-weight: 700;
  color: #1F4E79;
  letter-spacing: 8px;
  margin: 0;
}
.cert-excellent .cert-title {
  color: #B8860B;
}
.cert-subtitle {
  font-size: 11px;
  color: #999;
  letter-spacing: 4px;
  margin-top: 4px;
  font-family: 'Georgia', serif;
}

.cert-divider {
  width: 400px;
  height: 2px;
  background: linear-gradient(90deg, transparent, #1F4E79, transparent);
  margin: 16px 0 24px;
}
.cert-excellent .cert-divider {
  background: linear-gradient(90deg, transparent, #B8860B, transparent);
}

.cert-body {
  text-align: center;
  margin-bottom: 24px;
}
.cert-name {
  font-size: 28px;
  font-weight: 700;
  color: #333;
  margin: 0 0 20px;
  border-bottom: 1px solid #999;
  display: inline-block;
  padding: 0 20px 4px;
}
.cert-text {
  font-size: 18px;
  color: #444;
  line-height: 2;
  margin: 0;
}
.cert-level {
  font-size: 20px;
  font-weight: 700;
  color: #1F4E79;
  padding: 0 4px;
}
.cert-excellent .cert-level {
  color: #B8860B;
}

.cert-footer {
  text-align: center;
  margin-top: auto;
}
.cert-org {
  font-size: 16px;
  color: #555;
  letter-spacing: 2px;
}
.cert-date {
  font-size: 14px;
  color: #888;
  margin-top: 4px;
}
</style>
