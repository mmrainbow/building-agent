<template>
  <div>
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px">
      <h3 style="color:white;margin:0">图像巡检</h3>
      <el-tag type="info" v-if="!running && !result">至少需要 3 张图片</el-tag>
      <el-tag type="warning" v-if="running">巡检中...</el-tag>
      <el-tag type="success" v-if="result">巡检完成</el-tag>
    </div>

    <!-- 图片上传区 -->
    <div v-if="!result" style="margin-bottom:16px">
      <div v-if="!imgs.length" style="border:2px dashed #444;border-radius:12px;padding:60px 20px;text-align:center;cursor:pointer"
        @click="$refs.fileInput.click()" @dragover.prevent @drop.prevent="onDrop">
        <el-icon style="font-size:48px;color:#555"><Upload /></el-icon>
        <div style="color:#888;margin-top:12px">点击选择或拖拽建筑图片到此处</div>
        <div style="color:#555;font-size:12px;margin-top:4px">支持 JPG/PNG，至少 3 张不同角度</div>
      </div>

      <div v-else>
        <!-- 已选图片网格 -->
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">
          <div v-for="(img, i) in imgs" :key="i" style="position:relative;width:200px">
            <img :src="img.url" style="width:200px;height:150px;object-fit:cover;border-radius:8px;border:2px solid #333" />
            <div style="position:absolute;top:4px;left:4px;background:rgba(0,0,0,0.7);color:white;padding:2px 8px;border-radius:4px;font-size:12px">图{{ i+1 }}</div>
            <el-button size="small" circle type="danger" style="position:absolute;top:4px;right:4px"
              @click="imgs.splice(i,1)">✕</el-button>
            <div v-if="img.angles?.length" style="color:#22c55e;font-size:11px;padding:4px">{{ img.angles.join(', ') }}</div>
          </div>
        </div>
        <div style="display:flex;gap:8px">
          <input type="file" ref="fileInput" accept="image/*" multiple style="display:none" @change="onFilesChange" />
          <el-button @click="$refs.fileInput.click()">+ 添加更多图片</el-button>
          <el-button type="primary" size="large" @click="runInspection" :disabled="imgs.length<3" :loading="running">
            {{ imgs.length >= 3 ? `开始巡检 (${imgs.length} 张)` : `至少需要 3 张 (已有 ${imgs.length})` }}
          </el-button>
          <el-button @click="clearAll">清空重选</el-button>
        </div>
      </div>
    </div>

    <!-- 巡检结果 -->
    <div v-if="result" style="animation:fadeIn 0.5s">
      <div style="display:flex;gap:8px;margin-bottom:16px">
        <el-button @click="clearAll">← 开始新一轮巡检</el-button>
        <el-button @click="runInspection" :loading="running">重新检测</el-button>
      </div>

      <!-- 标注图片画廊 -->
      <div v-if="result.annotated_images?.length">
        <h4 style="color:#a78bfa;margin-bottom:8px">缺陷标注图</h4>
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px">
          <div v-for="(b64, i) in result.annotated_images" :key="i" style="text-align:center">
            <img :src="'data:image/jpeg;base64,'+b64"
              style="max-width:320px;max-height:280px;border-radius:8px;border:1px solid #444;cursor:pointer"
              @click="viewImage('data:image/jpeg;base64,'+b64)" />
            <div style="color:#888;font-size:12px;margin-top:4px">图{{ i+1 }} 标注结果</div>
          </div>
        </div>
      </div>

      <!-- 报告 -->
      <div style="background:#16213e;border-radius:12px;padding:24px">
        <h4 style="color:#60a5fa;margin-bottom:12px">巡检报告 #{{ result.record_id }}</h4>
        <div v-html="formatReport(result.report)" style="color:#ccc;font-size:15px;line-height:2"></div>
      </div>
    </div>

    <!-- 图片预览对话框 -->
    <el-dialog v-model="previewVisible" width="80%">
      <img :src="previewSrc" style="width:100%;border-radius:4px" />
    </el-dialog>

    <div v-if="error" style="color:#ef4444;margin-top:12px;padding:12px;background:#2d1b1b;border-radius:8px">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { inspectionAPI } from '../api/inspection'

const imgs = ref([])
const running = ref(false)
const result = ref(null)
const error = ref('')
const previewVisible = ref(false)
const previewSrc = ref('')
const fileInput = ref(null)

function onFilesChange(e) {
  for (const f of e.target.files) {
    imgs.value.push({ file: f, url: URL.createObjectURL(f), angles: [] })
  }
}
function onDrop(e) {
  for (const f of e.dataTransfer.files) {
    if (f.type.startsWith('image/')) imgs.value.push({ file: f, url: URL.createObjectURL(f), angles: [] })
  }
}
function clearAll() { imgs.value = []; result.value = null; error.value = '' }
function viewImage(src) { previewSrc.value = src; previewVisible.value = true }

function formatReport(text) {
  if (!text) return ''
  // 将报告文本转为 HTML 段落
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/^/, '<p>').replace(/$/, '</p>')
}

async function runInspection() {
  running.value = true; error.value = ''; result.value = null
  try {
    result.value = await inspectionAPI.multi(imgs.value.map(i => i.file))
  } catch(e) {
    error.value = e.response?.data?.detail || '巡检失败，请检查后端服务是否运行'
  }
  running.value = false
}
</script>

<style scoped>
@keyframes fadeIn { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }
</style>
