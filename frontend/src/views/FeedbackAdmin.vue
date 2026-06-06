<template>
  <div class="feedback-page">
    <div class="feedback-header">
      <div>
        <h3 class="feedback-title">管理员看板</h3>
        <p class="feedback-subtitle">系统使用概览、隐患分布与用户反馈闭环</p>
      </div>
      <el-button size="small" @click="load" :loading="loading">刷新</el-button>
    </div>

    <div class="stats-row">
      <el-card class="stat-card">
        <div class="stat-label">用户数</div>
        <div class="stat-value">{{ dashboard.user_count || 0 }}</div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">巡检次数</div>
        <div class="stat-value">{{ dashboard.inspection_count || 0 }}</div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">模型调用</div>
        <div class="stat-value">{{ dashboard.model_call_count || 0 }}</div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">反馈总数</div>
        <div class="stat-value">{{ stats.total || 0 }}</div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">平均评分</div>
        <div class="stat-value">{{ dashboard.average_rating || stats.average_rating || '-' }}</div>
      </el-card>
    </div>

    <div class="distribution-row">
      <el-card class="dist-card">
        <div class="stat-label">隐患类型分布</div>
        <div v-if="dashboard.defect_distribution?.length" class="dist-list">
          <div v-for="item in dashboard.defect_distribution" :key="item.name" class="dist-item">
            <span>{{ item.name }}</span>
            <strong>{{ item.count }}</strong>
          </div>
        </div>
        <div v-else class="empty-hint">暂无隐患数据</div>
      </el-card>
      <el-card class="dist-card">
        <div class="stat-label">材质分布</div>
        <div v-if="dashboard.material_distribution?.length" class="dist-list">
          <div v-for="item in dashboard.material_distribution" :key="item.name" class="dist-item">
            <span>{{ item.name }}</span>
            <strong>{{ item.count }}</strong>
          </div>
        </div>
        <div v-else class="empty-hint">暂无材质数据</div>
      </el-card>
      <el-card class="stat-card wide">
        <div class="stat-label">评分分布</div>
        <div class="rating-counts">
          <span v-for="n in [5,4,3,2,1]" :key="n">{{ n }}星：{{ stats.rating_counts?.[n] || 0 }}</span>
        </div>
      </el-card>
    </div>

    <h4 class="section-title">用户反馈明细</h4>
    <el-table :data="feedbacks" :loading="loading" class="feedback-table">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="用户" width="120" />
      <el-table-column label="评分" width="150">
        <template #default="{row}">
          <el-rate :model-value="row.rating || 0" disabled size="small" />
        </template>
      </el-table-column>
      <el-table-column label="意见" min-width="220">
        <template #default="{row}">{{ row.comment || '无文字意见' }}</template>
      </el-table-column>
      <el-table-column label="原始回复" min-width="320" show-overflow-tooltip>
        <template #default="{row}">{{ row.original_value || '-' }}</template>
      </el-table-column>
      <el-table-column label="时间" width="170">
        <template #default="{row}">{{ row.created_at?.slice(0,16)?.replace('T',' ') }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminAPI } from '../api/admin'

const feedbacks = ref([])
const stats = ref({})
const dashboard = ref({})
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const params = { feedback_type: 'chat_rating' }
    const [list, stat, dash] = await Promise.all([
      adminAPI.listFeedbacks(params),
      adminAPI.feedbackStats(params),
      adminAPI.dashboard(),
    ])
    feedbacks.value = list
    stats.value = stat
    dashboard.value = dash
  } catch (e) {
    ElMessage.error('反馈数据加载失败，请确认当前账号具备管理员权限')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.feedback-page { color: #4a4238; }
.feedback-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
.feedback-title { margin: 0; font-size: 18px; }
.feedback-subtitle { margin: 6px 0 0; color: #8a8278; font-size: 13px; }
.stats-row { display: flex; gap: 14px; margin-bottom: 16px; }
.stat-card { width: 150px; }
.stat-card.wide { flex: 1; }
.stat-label { color: #8a8278; font-size: 13px; margin-bottom: 8px; }
.stat-value { font-size: 28px; font-weight: 700; color: #6b7fa0; }
.distribution-row { display: grid; grid-template-columns: 1fr 1fr 1.2fr; gap: 14px; margin-bottom: 18px; }
.dist-card { min-height: 120px; }
.dist-list { display: flex; flex-direction: column; gap: 8px; }
.dist-item { display: flex; justify-content: space-between; color: #6b6054; }
.empty-hint { color: #b0a89e; font-size: 13px; }
.rating-counts { display: flex; gap: 14px; flex-wrap: wrap; color: #6b6054; }
.section-title { color: #6b6054; margin: 8px 0 12px; }
.feedback-table { border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.03); }
</style>
