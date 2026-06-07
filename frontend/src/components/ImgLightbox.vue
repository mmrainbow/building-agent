<template>
  <div class="img-lightbox" v-if="src" @click="src = ''">
    <span class="lightbox-close">x</span>
    <img :src="src" @click.stop />
  </div>
</template>

<script setup>
import { ref } from 'vue'
const src = ref('')
function show(s) { src.value = s }
function hide() { src.value = '' }
defineExpose({ show, hide })
</script>

<style scoped>
.img-lightbox {
  position: fixed; top: 0; right: 0; bottom: 0; left: 0;
  background: rgba(0,0,0,0.75); display: flex; align-items: center; justify-content: center;
  z-index: 9999; cursor: pointer;
}
.lightbox-close {
  position: fixed; top: 20px; right: 24px; color: #fff; font-size: 32px; font-weight: 300;
  cursor: pointer; z-index: 10000; width: 40px; height: 40px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.4); border-radius: 50%;
}
.lightbox-close:hover { background: rgba(0,0,0,0.6); }
.img-lightbox img { max-width: 85vw; max-height: 85vh; border-radius: 8px; box-shadow: 0 8px 40px rgba(0,0,0,0.4); cursor: default; }
</style>
