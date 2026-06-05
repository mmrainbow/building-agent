<template>
  <div class="monitor-page">
    <div class="monitor-header">
      <h3 class="monitor-title">Agent 监控</h3>
      <el-button @click="load" class="refresh-btn">刷新状态</el-button>
    </div>
    <div v-if="status" class="card-row">
      <el-card v-for="card in cards" :key="card.name" class="agent-card">
        <span class="card-dot" :style="{background:card.color}"></span>
        <span class="card-name">{{ card.name }}</span>
        <div class="card-model">{{ card.model }}</div>
        <div class="card-status" :style="{color:card.color}">{{ card.statusText }}</div>
      </el-card>
    </div>
    <TokenRing :current="status?.memory?.total_chars || 0" :threshold="status?.memory?.threshold || 6000" v-if="status" />
    <div class="monitor-hint">上下文用量: 所有活跃对话的累积字符数</div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import client from '../api/index'
import TokenRing from '../components/TokenRing.vue'

const status = ref(null)
const cards = computed(() => {
  if (!status.value) return []
  const s = status.value
  return [
    { name: '🧠 Manager', model: s.manager?.model, color: '#7eb89e', statusText: s.manager?.status },
    { name: '💾 Memory', model: 'qwen-turbo', color: s.memory?.pct > 80 ? '#c97b7b' : '#d4a574', statusText: `${s.memory?.total_chars}/${s.memory?.threshold} 字符` },
    { name: '📋 Report', model: 'Qwen2.5-VL', color: s.report?.status === 'online' ? '#7eb89e' : '#c97b7b', statusText: s.report?.status },
  ]
})
async function load() {
  try { const r = await client.get('/agent/status'); status.value = r.data } catch(e) {}
}
</script>

<style scoped>
.monitor-page { color: #4a4238; }
.monitor-header { display: flex; align-items: center; gap: 14px; margin-bottom: 20px; }
.monitor-title { color: #4a4238; margin: 0; font-size: 18px; }
.refresh-btn {
  --el-button-bg-color: #f3efe9;
  --el-button-border-color: #e0d9ce;
  --el-button-text-color: #6b6054;
}

.card-row { display: flex; gap: 18px; margin-bottom: 24px; }
.agent-card {
  flex: 1;
  background: #fff;
  border: 1px solid #e8e2d8;
  border-radius: 14px;
  text-align: center;
  padding: 24px;
  transition: border-color 0.25s, box-shadow 0.25s;
  box-shadow: 0 2px 6px rgba(0,0,0,0.03);
}
.agent-card:hover {
  border-color: #c5bdaf;
  box-shadow: 0 4px 16px rgba(0,0,0,0.06);
}
.agent-card :deep(.el-card__body) { padding: 0; }

.card-dot {
  display: inline-block;
  width: 10px; height: 10px;
  border-radius: 50%;
  margin-right: 10px;
}
.card-name { font-weight: 600; color: #4a4238; font-size: 15px; }
.card-model { color: #8a8278; font-size: 12px; margin: 8px 0 6px; }
.card-status { margin-top: 8px; font-size: 13px; font-weight: 500; }
.monitor-hint { color: #b0a89e; font-size: 12px; margin-top: 12px; text-align: center; }
</style>
