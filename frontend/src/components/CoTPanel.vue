<template>
  <div class="cot-panel" v-if="steps.length">
    <div class="cot-header" @click="expanded = !expanded">
      <span class="cot-toggle">{{ expanded ? '▼' : '▶' }}</span>
      🧠 Manager Agent 思考过程
      <span class="cot-count">({{ steps.length }} 步)</span>
    </div>
    <div v-if="expanded" class="cot-body">
      <div v-for="(s, i) in steps" :key="i" class="cot-step">
        <span v-if="s.type==='think'" class="cot-think">  💭 第{{ s.round }}轮: {{ s.content || '' }}</span>
        <span v-else-if="s.type==='tool' && s.status==='running'" class="cot-tool-running">  🔧 {{ s.name }} 执行中...</span>
        <span v-else-if="s.type==='tool' && s.status==='done'" class="cot-tool">  ✅ {{ s.name }} 完成{{ s.elapsed_ms ? ` (${s.elapsed_ms}ms)` : '' }}</span>
        <span v-else class="cot-done">  📝 共 {{ s.rounds }} 步 → 生成回答</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
const props = defineProps({
  steps: { type: Array, default: () => [] },
  defaultExpanded: { type: Boolean, default: true },
})
const expanded = ref(props.defaultExpanded)
</script>

<style scoped>
.cot-panel {
  background: #faf8f4;
  border: 1px solid #e8e2d8;
  border-radius: 12px;
  margin-bottom: 10px;
  font-size: 12px;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  overflow: hidden;
}
.cot-header {
  color: #b8906a;
  font-weight: 600;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: background 0.15s;
}
.cot-header:hover { background: #f5f1ec; }
.cot-toggle { font-size: 10px; width: 14px; flex-shrink: 0; }
.cot-count { color: #b0a89e; font-weight: 400; font-size: 11px; margin-left: auto; }
.cot-body { padding: 0 14px 12px; }
.cot-step { margin: 4px 0; line-height: 1.5; }
.cot-think { color: #8a8278; white-space: pre-wrap; word-break: break-word; }
.cot-tool { color: #7eb89e; }
.cot-tool-running { color: #d4a574; }
.cot-done { color: #6b7fa0; }
</style>
