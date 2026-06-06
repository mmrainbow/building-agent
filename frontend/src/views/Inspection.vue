<template>
  <div class="inspection-page" @click="onPageClick">
    <div class="inspect-header">
      <h3 class="inspect-title">图像巡检</h3>
      <el-tag type="info" v-if="!running && !result" class="inspect-tag">至少需要 3 张图片</el-tag>
      <el-tag type="warning" v-if="running" class="inspect-tag">巡检中...</el-tag>
      <el-tag type="success" v-if="result" class="inspect-tag">巡检完成</el-tag>
    </div>

    <!-- 图片上传区 -->
    <div v-if="!result" class="upload-section">
      <div v-if="!imgs.length" class="upload-dropzone"
        @click="$refs.fileInput.click()" @dragover.prevent @drop.prevent="onDrop">
        <el-icon class="upload-icon"><Upload /></el-icon>
        <div class="upload-text">点击选择或拖拽建筑图片到此处</div>
        <div class="upload-hint">支持 JPG/PNG，至少 3 张不同角度</div>
      </div>

      <div v-else>
        <div class="img-grid">
          <div v-for="(img, i) in imgs" :key="i" class="img-card">
            <img :src="img.url" class="img-thumb" />
            <span class="img-badge">图{{ i+1 }}</span>
            <el-button size="small" circle type="danger" class="img-remove"
              @click="imgs.splice(i,1)">✕</el-button>
            <div v-if="img.angles?.length" class="img-angles">{{ img.angles.join(', ') }}</div>
          </div>
        </div>
        <div class="img-actions">
          <input type="file" ref="fileInput" accept="image/*" multiple class="file-hidden" @change="onFilesChange" />
          <el-button @click="$refs.fileInput.click()">+ 添加更多图片</el-button>
          <el-button type="primary" size="large" @click="runInspection" :disabled="imgs.length<3" :loading="running" class="run-btn">
            {{ imgs.length >= 3 ? `开始巡检 (${imgs.length} 张)` : `至少需要 3 张 (已有 ${imgs.length})` }}
          </el-button>
          <el-button @click="clearAll">清空重选</el-button>
        </div>
      </div>
    </div>

    <!-- 巡检结果 -->
    <div v-if="result" class="result-section">
      <div class="result-actions">
        <el-button @click="clearAll">← 开始新一轮巡检</el-button>
        <el-button @click="runInspection" :loading="running">重新检测</el-button>
      </div>

      <div v-if="result.annotated_images?.length" class="gallery-section">
        <h4 class="gallery-title">缺陷标注图</h4>
        <div class="gallery-grid">
          <div v-for="(b64, i) in result.annotated_images" :key="i" class="gallery-item">
            <img :src="'data:image/jpeg;base64,'+b64"
              class="gallery-img"
              style="cursor:pointer" />
            <div class="gallery-label">图{{ i+1 }} 标注结果</div>
          </div>
        </div>
      </div>

      <div class="report-card">
        <h4 class="report-title">巡检报告 #{{ result.record_id }}</h4>
        <div v-html="formatReport(result.report)" class="report-body"></div>
      </div>
    </div>

    <!-- 图片灯箱 -->
    <div class="img-lightbox" v-if="lightboxSrc" @click="lightboxSrc = null">
      <span class="lightbox-close">×</span>
      <img :src="lightboxSrc" @click.stop />
    </div>

    <div v-if="error" class="error-box">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { inspectionAPI } from '../api/inspection'

const imgs = ref([])
const running = ref(false)
const result = ref(null)
const error = ref('')
const lightboxSrc = ref(null)
const fileInput = ref(null)

function onPageClick(e) {
  if (e.target.tagName === 'IMG' && e.target.src.startsWith('data:image')) {
    lightboxSrc.value = e.target.src
  }
}

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

function formatReport(text) {
  if (!text) return ''
  let html = text
  // 保留 <img>，其余 HTML 转义
  const imgs = []; html = html.replace(/<img[^>]+>/gi, m => { imgs.push(m); return `\x00IMG${imgs.length-1}\x00` })
  html = html.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  html = html.replace(/\x00IMG(\d+)\x00/g, (_,i) => imgs[+i])
  // Markdown → HTML
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/((?:^- .+\n?)+)/gm, m => '<ul>' + m.trim().split('\n').map(l => '<li>'+l.replace(/^- /,'')+'</li>').join('') + '</ul>')
  html = html.replace(/((?:^\d+\. .+\n?)+)/gm, m => '<ol>' + m.trim().split('\n').map(l => '<li>'+l.replace(/^\d+\. /,'')+'</li>').join('') + '</ol>')
  html = html.replace(/\n\n+/g, '</p><p>')
  html = html.replace(/\n/g, '<br>')
  html = '<p>' + html + '</p>'
  html = html.replace(/<p><\/p>/g, '')
  html = html.replace(/<p>(<[ou]l>)/g, '$1')
  html = html.replace(/(<\/[ou]l>)<\/p>/g, '$1')
  return html
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
.inspection-page { color: #4a4238; }

.inspect-header { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
.inspect-title { color: #4a4238; margin: 0; font-size: 18px; }
.inspect-tag {
  --el-tag-bg-color: #f5f1ec;
  --el-tag-border-color: #e0d9ce;
  --el-tag-text-color: #6b6054;
}

.upload-section { margin-bottom: 16px; }
.upload-dropzone {
  border: 2px dashed #e0d9ce;
  border-radius: 16px;
  padding: 64px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.25s ease;
  background: #fff;
}
.upload-dropzone:hover { border-color: #8b9ec9; background: #faf8f4; }
.upload-icon { font-size: 52px; color: #c5bdaf; }
.upload-text { color: #8a8278; margin-top: 14px; font-size: 15px; }
.upload-hint { color: #b0a89e; font-size: 12px; margin-top: 8px; }

.img-grid { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 18px; }
.img-card { position: relative; width: 200px; }
.img-thumb {
  width: 200px; height: 150px;
  object-fit: contain;
  background: #faf8f4;
  border-radius: 12px;
  border: 2px solid #e8e2d8;
  transition: border-color 0.2s;
}
.img-thumb:hover { border-color: #c5bdaf; }
.img-badge {
  position: absolute; top: 8px; left: 8px;
  background: rgba(74,66,56,0.75); color: #faf8f4;
  padding: 3px 10px; border-radius: 6px; font-size: 12px;
}
.img-remove { position: absolute; top: 8px; right: 8px; }
.img-angles { color: #7eb89e; font-size: 11px; padding: 4px; }
.img-actions { display: flex; gap: 10px; }
.file-hidden { display: none; }
.run-btn { --el-button-bg-color: #6b7fa0; --el-button-border-color: #6b7fa0; }

.result-section { animation: fadeIn 0.5s ease; }
.result-actions { display: flex; gap: 10px; margin-bottom: 18px; }
.gallery-section { margin-bottom: 20px; }
.gallery-title { color: #6b6054; margin-bottom: 12px; font-size: 15px; }
.gallery-grid { display: flex; gap: 14px; flex-wrap: wrap; }
.gallery-item { text-align: center; }
.gallery-img {
  max-width: 320px; max-height: 280px;
  border-radius: 12px; border: 1px solid #e8e2d8;
  cursor: pointer; transition: transform 0.2s, box-shadow 0.2s;
  object-fit: contain;
}
.gallery-img:hover { transform: scale(1.02); box-shadow: 0 4px 16px rgba(0,0,0,0.08); }
.gallery-label { color: #8a8278; font-size: 12px; margin-top: 8px; }

.report-card {
  background: #fff;
  border-radius: 16px;
  padding: 28px;
  border: 1px solid #e8e2d8;
  box-shadow: 0 2px 8px rgba(0,0,0,0.03);
}
.report-title { color: #6b7fa0; margin-bottom: 16px; font-size: 16px; }
.report-body { color: #4a4238; font-size: 15px; line-height: 2; }

.preview-img { width: 100%; border-radius: 8px; }
.error-box {
  color: #c97b7b; margin-top: 14px;
  padding: 14px; background: #fdf2f2;
  border-radius: 12px; border: 1px solid #f0d0d0;
}

/* ── 图片灯箱 ── */
.img-lightbox {
  position: fixed; top: 0; right: 0; bottom: 0; left: 0;
  background: rgba(0,0,0,0.75);
  display: flex; align-items: center; justify-content: center;
  z-index: 9999; cursor: pointer;
}
.lightbox-close {
  position: fixed; top: 20px; right: 24px;
  color: #fff; font-size: 32px; font-weight: 300;
  cursor: pointer; z-index: 10000;
  width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.4); border-radius: 50%;
}
.lightbox-close:hover { background: rgba(0,0,0,0.6); }
.img-lightbox img {
  max-width: 85vw; max-height: 85vh;
  border-radius: 8px; box-shadow: 0 8px 40px rgba(0,0,0,0.4);
  cursor: default;
}

@keyframes fadeIn { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }
</style>
