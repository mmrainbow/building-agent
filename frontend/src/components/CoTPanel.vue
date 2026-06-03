<template>
  <div style="background:#111;border:1px solid #333;border-radius:8px;padding:10px;margin-bottom:8px;font-size:12px;font-family:monospace">
    <div style="color:#f59e0b;font-weight:bold;margin-bottom:6px">🧠 Manager Agent 思考过程</div>
    <div v-for="(s, i) in steps" :key="i" style="margin:2px 0">
      <span v-if="s.type==='think'" style="color:#94a3b8">  💭 第{{ s.round }}轮: {{ (s.content||'').slice(0,60) }}</span>
      <span v-else style="color:#22c55e">  ✅ {{ s.name }} 完成{{ s.elapsed_ms ? ` (${s.elapsed_ms}ms)` : '' }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({ steps: { type: Array, default: () => [] } })
</script>
