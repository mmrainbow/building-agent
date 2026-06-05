<template>
  <div class="ring-wrap">
    <svg width="100" height="100" viewBox="0 0 36 36">
      <circle cx="18" cy="18" r="15.5" fill="none" stroke="#e8e2d8" stroke-width="3"/>
      <circle cx="18" cy="18" r="15.5" fill="none" :stroke="color" stroke-width="3"
        :stroke-dasharray="`${pct} ${100-pct}`" stroke-dashoffset="25" stroke-linecap="round"
        transform="rotate(-90 18 18)"/>
      <text x="18" y="16" text-anchor="middle" fill="#4a4238" font-size="7" font-weight="bold">{{ pct }}%</text>
      <text x="18" y="23" text-anchor="middle" fill="#8a8278" font-size="4">{{ current }}/{{ threshold }}</text>
    </svg>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ current: Number, threshold: Number })
const pct = computed(() => Math.min(Math.round(props.current / props.threshold * 100), 100))
const color = computed(() => pct.value < 50 ? '#7eb89e' : pct.value < 80 ? '#d4a574' : '#c97b7b')
</script>

<style scoped>
.ring-wrap { text-align: center; }
</style>
