<template>
  <div class="page-container">
    <a-card v-if="loading" :bordered="false">
      <a-skeleton active :paragraph="{ rows: 10 }" />
    </a-card>

    <template v-else-if="diagnostic">
      <div class="report-actions">
        <a-button @click="returnToScores">
          <LeftOutlined /> 返回成绩页
        </a-button>
        <a-space>
          <a-button type="primary" :loading="downloading" @click="downloadReport">
            <DownloadOutlined /> 下载报告
          </a-button>
          <a-button
            :loading="downloadingCert"
            :disabled="!canDownloadCert"
            @click="downloadCert"
            :style="canDownloadCert ? certButtonStyle : {}"
          >
            <SafetyCertificateOutlined /> 下载证书
          </a-button>
        </a-space>
      </div>
      <div ref="reportRef">
        <DiagnosticReportView
          :diagnostic="diagnostic"
          :user-name="diagnosticUserName"
          :full-review-data="fullReviewData"
          :full-review-loading="fullReviewLoading"
          :open-complaint="openComplaintModal"
        />
      </div>
    </template>

    <a-card v-else :bordered="false">
      <a-result
        status="error"
        title="诊断报告加载失败"
        :sub-title="errorMessage || '暂时无法获取诊断报告，请稍后重试。'"
      >
        <template #extra>
          <a-space wrap>
            <a-button type="primary" @click="fetchDiagnostic">重试</a-button>
            <a-button @click="returnToScores">返回成绩页</a-button>
          </a-space>
        </template>
      </a-result>
    </a-card>

    <a-modal
      v-model:open="complaintModalVisible"
      title="评分反馈投诉"
      :confirm-loading="complaintSubmitting"
      ok-text="提交反馈"
      cancel-text="取消"
      @ok="submitComplaint"
    >
      <div v-if="complaintTargetDetail" class="complaint-target">
        <div class="complaint-row"><strong>题目：</strong>第 {{ complaintTargetDetail.order_num }} 题（{{ typeLabel(complaintTargetDetail.question_type) }}）</div>
        <div class="complaint-row"><strong>得分：</strong>{{ complaintTargetDetail.earned_score }} / {{ complaintTargetDetail.max_score }}</div>
        <div class="complaint-stem">{{ complaintTargetDetail.stem?.substring(0, 80) }}{{ complaintTargetDetail.stem?.length > 80 ? '...' : '' }}</div>
      </div>
      <a-textarea
        v-model:value="complaintReason"
        placeholder="请详细描述您认为评分有误的原因，例如：答案选择了B但被判为错误，实际B也是正确答案..."
        :rows="4"
        :maxlength="2000"
        show-count
      />
    </a-modal>

    <div ref="certRef" class="cert-container" :class="{ 'cert-excellent': certLevel === '优秀' }">
      <div class="cert-border">
        <div class="cert-inner">
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
            <p class="cert-name">{{ diagnosticUserName }}</p>
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
import { computed, onMounted, ref, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { DownloadOutlined, LeftOutlined, SafetyCertificateOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'
import request from '@/utils/request'
import { useUserStore } from '@/stores/user'
import { exportElementToPdf } from '@/utils/pdfExport'
import DiagnosticReportView from '@/components/DiagnosticReportView.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const downloading = ref(false)
const downloadingCert = ref(false)
const diagnostic = ref<any>(null)
const errorMessage = ref('')
const reportRef = ref<HTMLElement | null>(null)
const certRef = ref<HTMLElement | null>(null)
const fullReviewData = ref<any>(null)
const fullReviewLoading = ref(false)
const complaintModalVisible = ref(false)
const complaintTargetDetail = ref<any>(null)
const complaintReason = ref('')
const complaintSubmitting = ref(false)

const scoreId = computed(() => String(route.params.scoreId || ''))
const diagnosticUserName = computed(() => {
  const queryName = route.query.displayName
  if (typeof queryName === 'string' && queryName.trim()) {
    return queryName
  }
  return userStore.userInfo?.full_name || userStore.userInfo?.username || '用户'
})
const canDownloadCert = computed(() => ['优秀', '良好', '合格'].includes(diagnostic.value?.level))
const certLevel = computed(() => (diagnostic.value?.level === '优秀' ? '优秀' : '合格'))
const certButtonStyle = computed(() => ({
  background: certLevel.value === '优秀' ? '#B8860B' : '#1F4E79',
  borderColor: certLevel.value === '优秀' ? '#B8860B' : '#1F4E79',
  color: '#fff',
}))
const certDate = computed(() => {
  const now = new Date()
  return `${now.getFullYear()}年${now.getMonth() + 1}月`
})

async function fetchDiagnostic() {
  if (!scoreId.value) return
  loading.value = true
  errorMessage.value = ''
  fullReviewData.value = null
  void fetchFullReview()
  try {
    diagnostic.value = await request.get(`/scores/${scoreId.value}/diagnostic`)
  } catch (error: any) {
    diagnostic.value = null
    errorMessage.value = error?.message || '诊断报告加载失败'
  } finally {
    loading.value = false
  }
}

async function fetchFullReview() {
  if (!scoreId.value) return
  fullReviewLoading.value = true
  try {
    fullReviewData.value = await request.get(`/scores/${scoreId.value}/full-review`)
  } catch {
    fullReviewData.value = null
  } finally {
    fullReviewLoading.value = false
  }
}

function openComplaintModal(item: any) {
  complaintTargetDetail.value = item
  complaintReason.value = ''
  complaintModalVisible.value = true
}

async function submitComplaint() {
  if (!complaintReason.value.trim()) {
    message.warning('请输入反馈原因')
    return
  }
  complaintSubmitting.value = true
  try {
    await request.post('/scores/complaints', {
      score_detail_id: complaintTargetDetail.value.score_detail_id,
      reason: complaintReason.value,
    })
    message.success('反馈已提交，我们会尽快处理')
    complaintModalVisible.value = false
  } catch (error: any) {
    message.error(error?.message || '反馈提交失败，请重试')
  } finally {
    complaintSubmitting.value = false
  }
}

function typeLabel(type: string): string {
  const map: Record<string, string> = {
    single_choice: '单选题',
    multiple_choice: '多选题',
    true_false: '判断题',
    fill_blank: '填空题',
    short_answer: '简答题',
  }
  return map[type] || type
}

function returnToScores() {
  router.push({ name: 'Scores' })
}

async function downloadReport() {
  if (!reportRef.value || !diagnostic.value) return
  downloading.value = true
  try {
    await exportElementToPdf(reportRef.value, {
      filename: 'AI素养诊断分析报告.pdf',
      backgroundColor: '#f0f2f5',
      scale: 1.5,
      imageQuality: 0.78,
    })
    message.success('报告下载成功')
  } catch {
    message.error('报告下载失败，请重试')
  } finally {
    downloading.value = false
  }
}

async function downloadCert() {
  if (!certRef.value || !canDownloadCert.value) return
  downloadingCert.value = true
  try {
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
    pdf.save(`${diagnosticUserName.value}AI素养评测证书.pdf`)
    message.success('证书下载成功')
  } catch {
    message.error('证书下载失败，请重试')
  } finally {
    if (certRef.value) {
      certRef.value.style.left = '-9999px'
      certRef.value.style.opacity = '0'
    }
    downloadingCert.value = false
  }
}

watch(scoreId, () => {
  fetchDiagnostic()
})

onMounted(() => {
  fetchDiagnostic()
})
</script>

<style scoped>
.report-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.complaint-target {
  margin-bottom: 16px;
  padding: 12px;
  background: #f5f5f5;
  border-radius: 6px;
}

.complaint-row {
  margin-bottom: 4px;
}

.complaint-stem {
  color: #666;
  font-size: 13px;
}

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
