<template>
  <div class="cot-panel">
    <div class="cot-header">🧠 Manager Agent 思考过程</div>
    <div v-for="(s, i) in steps" :key="i" class="cot-step">
      <span v-if="s.type==='think'" class="cot-think">  💭 第{{ s.round }}轮: {{ (s.content||'').slice(0,60) }}</span>
      <span v-else class="cot-tool">  ✅ {{ s.name }} 完成{{ s.elapsed_ms ? ` (${s.elapsed_ms}ms)` : '' }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({ steps: { type: Array, default: () => [] } })
</script>

<style scoped>
.cot-panel {
  background: #faf8f4;
  border: 1px solid #e8e2d8;
  border-radius: 12px;
  padding: 14px;
  margin-bottom: 10px;
  font-size: 12px;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
}
.cot-header { color: #b8906a; font-weight: 600; margin-bottom: 10px; }
.cot-step { margin: 4px 0; }
.cot-think { color: #8a8278; }
.cot-tool { color: #7eb89e; }
</style>
