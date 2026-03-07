<template>
  <div class="page-container">
    <div class="page-header">
      <h2>首页</h2>
    </div>
    <a-row :gutter="[24, 24]">
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card hoverable @click="$router.push({ name: 'Materials' })">
          <a-statistic title="素材总量" :value="stats.materials">
            <template #prefix><FolderOutlined /></template>
          </a-statistic>
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card hoverable @click="$router.push({ name: 'Questions' })">
          <a-statistic title="题库题目" :value="stats.questions">
            <template #prefix><FileTextOutlined /></template>
          </a-statistic>
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card hoverable @click="$router.push({ name: 'Exams' })">
          <a-statistic title="考试场次" :value="stats.exams">
            <template #prefix><FormOutlined /></template>
          </a-statistic>
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card hoverable>
          <a-statistic title="参与人数" :value="stats.users">
            <template #prefix><TeamOutlined /></template>
          </a-statistic>
        </a-card>
      </a-col>
    </a-row>

    <a-row :gutter="[24, 24]" style="margin-top: 24px;">
      <a-col :xs="24" :lg="16">
        <a-card title="快速入口" class="card-container">
          <a-row :gutter="16">
            <a-col :span="8">
              <a-button type="primary" block size="large" @click="$router.push({ name: 'Materials' })">
                上传素材
              </a-button>
            </a-col>
            <a-col :span="8">
              <a-button block size="large" @click="$router.push({ name: 'Questions' })">
                管理题库
              </a-button>
            </a-col>
            <a-col :span="8">
              <a-button block size="large" @click="$router.push({ name: 'Exams' })">
                创建考试
              </a-button>
            </a-col>
          </a-row>
        </a-card>
      </a-col>
      <a-col :xs="24" :lg="8">
        <a-card title="系统公告" class="card-container">
          <a-empty description="暂无公告" />
        </a-card>
      </a-col>
    </a-row>

    <!-- Leaderboard Summary -->
    <a-row :gutter="[24, 24]" style="margin-top: 24px;">
      <a-col :span="24">
        <a-card :bordered="false" class="home-leaderboard-card">
          <template #title>
            <span class="home-lb-title">🏆 英雄榜</span>
          </template>
          <template #extra>
            <a-button type="link" @click="$router.push({ name: 'Scores' })">查看完整榜单 →</a-button>
          </template>
          <a-spin :spinning="leaderboardLoading">
            <div class="home-lb-list" v-if="leaderboard.length > 0">
              <div
                v-for="(item, idx) in leaderboard"
                :key="item.user_id"
                class="home-lb-item"
              >
                <div class="home-lb-rank">
                  <span v-if="idx === 0" style="font-size: 22px;">🥇</span>
                  <span v-else-if="idx === 1" style="font-size: 22px;">🥈</span>
                  <span v-else-if="idx === 2" style="font-size: 22px;">🥉</span>
                  <span v-else class="home-lb-rank-num">{{ idx + 1 }}</span>
                </div>
                <div class="home-lb-info">
                  <span class="home-lb-name">{{ item.full_name || item.username }}</span>
                </div>
                <div class="home-lb-score">
                  <strong>{{ item.score_ratio }}%</strong>
                </div>
                <div class="home-lb-level">
                  <a-tag :color="levelColor(item.level)" size="small">{{ item.level }}</a-tag>
                </div>
              </div>
            </div>
            <a-empty v-else description="暂无排名数据" :image="simpleImage" />
          </a-spin>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  FolderOutlined,
  FileTextOutlined,
  FormOutlined,
  TeamOutlined,
} from '@ant-design/icons-vue'
import { Empty } from 'ant-design-vue'
import request from '@/utils/request'

const simpleImage = Empty.PRESENTED_IMAGE_SIMPLE

const stats = ref({
  materials: 0,
  questions: 0,
  exams: 0,
  users: 0,
})

const leaderboard = ref<any[]>([])
const leaderboardLoading = ref(false)

function levelColor(level: string): string {
  const map: Record<string, string> = {
    '优秀': 'green', '良好': 'blue', '合格': 'orange', '不合格': 'red', '需提升': 'red',
  }
  return map[level] || 'default'
}

async function loadStats() {
  const results = await Promise.allSettled([
    request.get('/materials', { params: { skip: 0, limit: 1 } }),
    request.get('/questions', { params: { skip: 0, limit: 1 } }),
    request.get('/exams', { params: { skip: 0, limit: 1 } }),
    request.get('/users', { params: { skip: 0, limit: 1 } }),
  ])
  if (results[0].status === 'fulfilled') stats.value.materials = (results[0].value as any).total || 0
  if (results[1].status === 'fulfilled') stats.value.questions = (results[1].value as any).total || 0
  if (results[2].status === 'fulfilled') stats.value.exams = (results[2].value as any).total || 0
  if (results[3].status === 'fulfilled') stats.value.users = (results[3].value as any).total || 0
}

async function loadLeaderboard() {
  leaderboardLoading.value = true
  try {
    const data: any = await request.get('/scores/leaderboard', { params: { limit: 5 } })
    leaderboard.value = data.items || []
  } catch {
    leaderboard.value = []
  } finally {
    leaderboardLoading.value = false
  }
}

onMounted(() => {
  loadStats()
  loadLeaderboard()
})
</script>

<style scoped>
.home-leaderboard-card {
  background: linear-gradient(135deg, #fff9e6 0%, #fff3cd 50%, #ffeeba 100%);
  border: 1px solid #ffd700;
}
.home-lb-title {
  font-size: 18px;
  font-weight: 700;
  color: #8B6914;
}
.home-lb-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.home-lb-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 8px;
  transition: background 0.2s;
}
.home-lb-item:hover {
  background: rgba(255, 255, 255, 0.95);
}
.home-lb-rank {
  width: 36px;
  text-align: center;
  flex-shrink: 0;
}
.home-lb-rank-num {
  font-size: 16px;
  font-weight: 700;
  color: #8B6914;
}
.home-lb-info {
  flex: 1;
  min-width: 0;
}
.home-lb-name {
  font-size: 15px;
  font-weight: 600;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.home-lb-score {
  font-size: 15px;
  color: #8B6914;
  flex-shrink: 0;
}
.home-lb-level {
  flex-shrink: 0;
}
</style>
