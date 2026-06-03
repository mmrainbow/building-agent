<template>
  <div>
    <h3 style="color:white">Agent 监控</h3>
    <el-button @click="load" style="margin-bottom:12px">刷新状态</el-button>
    <div v-if="status" style="display:flex;gap:16px;margin-bottom:16px">
      <el-card v-for="card in cards" :key="card.name" style="flex:1;background:#16213e;text-align:center">
        <div style="display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px" :style="{background:card.color}"></div>
        <span style="font-weight:bold;color:white">{{ card.name }}</span>
        <div style="color:#888;font-size:12px">{{ card.model }}</div>
        <div style="margin-top:4px;font-size:13px" :style="{color:card.color}">{{ card.statusText }}</div>
      </el-card>
    </div>
    <TokenRing :current="status?.memory?.total_chars || 0" :threshold="status?.memory?.threshold || 6000" v-if="status" />
    <div style="color:#888;font-size:12px;margin-top:8px">上下文用量: 所有活跃对话的累积字符数</div>
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
    { name: '🧠 Manager', model: s.manager?.model, color: '#22c55e', statusText: s.manager?.status },
    { name: '💾 Memory', model: 'qwen-turbo', color: s.memory?.pct > 80 ? '#ef4444' : '#f59e0b', statusText: `${s.memory?.total_chars}/${s.memory?.threshold} 字符` },
    { name: '📋 Report', model: 'Qwen2.5-VL', color: s.report?.status === 'online' ? '#22c55e' : '#ef4444', statusText: s.report?.status },
  ]
})
async function load() {
  try { const r = await client.get('/agent/status'); status.value = r.data } catch(e) {}
}
</script>
