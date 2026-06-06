<template>
  <div class="inspection-page" @click="onPageClick">
    <div class="inspect-header">
      <h3 class="inspect-title">图像巡检</h3>
      <el-tag v-if="!running && !result" class="inspect-tag">至少 3 张图片</el-tag>
      <el-tag type="warning" v-if="running" class="inspect-tag">{{ progressLabel }}</el-tag>
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
            <el-button size="small" circle type="danger" class="img-remove" @click="imgs.splice(i,1)">×</el-button>
          </div>
        </div>
        <div class="img-actions">
          <input type="file" ref="fileInput" accept="image/*" multiple class="file-hidden" @change="onFilesChange" />
          <el-button @click="$refs.fileInput.click()">+ 添加更多</el-button>
          <el-button type="primary" size="large" @click="runInspection" :disabled="imgs.length<3" :loading="running" class="run-btn">
            {{ imgs.length >= 3 ? `开始巡检 (${imgs.length} 张)` : `至少 3 张 (已有 ${imgs.length})` }}
          </el-button>
          <el-button @click="clearAll">清空</el-button>
        </div>
      </div>
    </div>

    <!-- 进度条 -->
    <div v-if="running" class="progress-section">
      <el-progress :percentage="progressPct" :stroke-width="8" :color="progressPct===100?'#7eb89e':'#6b7fa0'" />
      <div class="progress-detail">{{ progressDetail }}</div>
    </div>

    <!-- 巡检结果 -->
    <div v-if="result" class="result-section">
      <div class="result-actions">
        <el-button @click="clearAll">← 新一轮巡检</el-button>
        <el-button @click="runInspection" :loading="running">重新检测</el-button>
        <span class="record-id">巡检 #{{ result.record_id }}</span>
      </div>

      <!-- CV 检测摘要 -->
      <div v-if="result.images?.length" class="cv-summary">
        <h4 class="section-title">CV 检测摘要</h4>
        <div class="cv-grid">
          <div v-for="img in result.images" :key="img.index" class="cv-card">
            <div class="cv-card-header">图{{ img.index }}</div>
            <div class="cv-items">
              <div class="cv-item"><span class="cv-label">材质</span><span class="cv-val">{{ img.material || '-' }}</span></div>
              <div class="cv-item"><span class="cv-label">楼层</span><span class="cv-val">{{ img.floor || '-' }}</span></div>
              <div class="cv-item"><span class="cv-label">加层</span><span class="cv-val">{{ img.has_extension || '-' }}</span></div>
              <div class="cv-item">
                <span class="cv-label">隐患</span>
                <span class="cv-val" v-if="!img.defects?.length">无</span>
                <span v-else class="cv-defects">
                  <span v-for="d in img.defects" :key="d.id" class="cv-defect-tag" :style="{borderColor: defectColor(d.type)}">
                    {{ d.type }}
                  </span>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 缺陷图例 -->
      <div v-if="hasDefects" class="legend-bar">
        <span v-for="c in defectLegend" :key="c.type" class="legend-item">
          <span class="legend-dot" :style="{background:c.color}"></span> {{ c.type }}
        </span>
      </div>

      <!-- 标注图 -->
      <div v-if="result.annotated_images?.length" class="gallery-section">
        <h4 class="section-title">缺陷标注图</h4>
        <div class="gallery-grid">
          <div v-for="(b64, i) in result.annotated_images" :key="i" class="gallery-item">
            <img :src="'data:image/jpeg;base64,'+b64" class="gallery-img" style="cursor:pointer" />
            <div class="gallery-label">图{{ i+1 }}</div>
          </div>
        </div>
      </div>

      <!-- 巡检报告 -->
      <div class="report-card">
        <h4 class="section-title">巡检报告</h4>
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
import { ref, computed } from 'vue'
import { inspectionAPI } from '../api/inspection'

const imgs = ref([])
const running = ref(false)
const result = ref(null)
const error = ref('')
const lightboxSrc = ref(null)
const fileInput = ref(null)
const progressPct = ref(0)
const progressDetail = ref('')

const progressLabel = computed(() => progressPct.value < 100 ? `检测中 ${progressPct.value}%` : '生成报告中...')
const hasDefects = computed(() => result.value?.images?.some(img => img.defects?.length))

const defectColors = { '空鼓': '#e74c3c', '渗水': '#3498db', '脱落': '#e67e22', '裂缝': '#f1c40f' }
const defectLegend = Object.entries(defectColors).map(([type, color]) => ({ type, color }))
function defectColor(type) { return defectColors[type] || '#999' }

function onPageClick(e) {
  if (e.target.tagName === 'IMG' && e.target.src.startsWith('data:image')) lightboxSrc.value = e.target.src
}

function onFilesChange(e) {
  for (const f of e.target.files) imgs.value.push({ file: f, url: URL.createObjectURL(f) })
}
function onDrop(e) {
  for (const f of e.dataTransfer.files) { if (f.type.startsWith('image/')) imgs.value.push({ file: f, url: URL.createObjectURL(f) }) }
}
function clearAll() { imgs.value = []; result.value = null; error.value = ''; progressPct.value = 0 }

function formatReport(text) {
  if (!text) return ''
  // 清除旧记录可能残留的 HTML 标签（标注图已由 Gallery 独立展示）
  let html = text.replace(/<div[^>]*>/gi, '').replace(/<\/div>/gi, '')
  html = html.replace(/<img[^>]*>/gi, '')
  // 转义 & 保留输出
  html = html.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  // Markdown → HTML
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/((?:^- .+\n?)+)/gm, m => '<ul>' + m.trim().split('\n').map(l => '<li>'+l.replace(/^- /,'')+'</li>').join('') + '</ul>')
  html = html.replace(/((?:^\d+\. .+\n?)+)/gm, m => '<ol>' + m.trim().split('\n').map(l => '<li>'+l.replace(/^\d+\. /,'')+'</li>').join('') + '</ol>')
  html = html.replace(/\n\n+/g, '</p><p>').replace(/\n/g, '<br>')
  html = '<p>' + html + '</p>'
  return html.replace(/<p><\/p>/g, '').replace(/<p>(<[ou]l>)/g, '$1').replace(/(<\/[ou]l>)<\/p>/g, '$1')
}

async function runInspection() {
  running.value = true; error.value = ''; result.value = null
  progressPct.value = 0; progressDetail.value = ''

  try {
    const token = localStorage.getItem('token')
    const form = new FormData()
    imgs.value.forEach(i => form.append('images', i.file))
    const params = new URLSearchParams({ stream: 'true' })
    const resp = await fetch(`/api/inspection/multi?${params}`, {
      method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: form,
    })
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const evt = JSON.parse(line.slice(6))
        if (evt.type === 'start') {
          progressDetail.value = `共 ${evt.total} 张图片，正在检测...`
        } else if (evt.type === 'step') {
          progressDetail.value = `图${evt.image}/${evt.total} — ${evt.label}`
          // 估算进度：每张图4个CV步骤 + 1个报告步骤
          const cvSteps = evt.total * 4
          const stepIdx = (evt.image - 1) * 4 + (evt.tool === 'material' ? 0 : evt.tool === 'floor' ? 1 : evt.tool === 'extension' ? 2 : 3)
          progressPct.value = Math.round(stepIdx / cvSteps * 85)
        } else if (evt.type === 'cv_done') {
          // 每张图 CV 完成
          const done = result.value?.images?.length || 0
          progressPct.value = Math.round((done + 1) / evt.total * 85)
        } else if (evt.type === 'done') {
          progressPct.value = 100
          progressDetail.value = '巡检完成'
          result.value = evt
          running.value = false
        }
      }
    }
  } catch (e) {
    error.value = e.message || '巡检失败'
  }
  running.value = false
}
</script>

<style scoped>
.inspection-page { color: #4a4238; }
.inspect-header { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
.inspect-title { color: #4a4238; margin: 0; font-size: 18px; }
.inspect-tag { --el-tag-bg-color: #f5f1ec; --el-tag-border-color: #e0d9ce; --el-tag-text-color: #6b6054; }
.record-id { color: #8a8278; font-size: 13px; margin-left: auto; }

.upload-section { margin-bottom: 16px; }
.upload-dropzone {
  border: 2px dashed #e0d9ce; border-radius: 16px; padding: 64px 20px; text-align: center;
  cursor: pointer; transition: all 0.25s ease; background: #fff;
}
.upload-dropzone:hover { border-color: #8b9ec9; background: #faf8f4; }
.upload-icon { font-size: 52px; color: #c5bdaf; }
.upload-text { color: #8a8278; margin-top: 14px; font-size: 15px; }
.upload-hint { color: #b0a89e; font-size: 12px; margin-top: 8px; }

.img-grid { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 18px; }
.img-card { position: relative; width: 200px; }
.img-thumb { width: 200px; height: 150px; object-fit: contain; background: #faf8f4; border-radius: 12px; border: 2px solid #e8e2d8; }
.img-badge { position: absolute; top: 8px; left: 8px; background: rgba(74,66,56,0.75); color: #faf8f4; padding: 3px 10px; border-radius: 6px; font-size: 12px; }
.img-remove { position: absolute; top: 8px; right: 8px; }
.img-actions { display: flex; gap: 10px; }
.file-hidden { display: none; }
.run-btn { --el-button-bg-color: #6b7fa0; --el-button-border-color: #6b7fa0; }

.progress-section { margin: 20px 0 30px; }
.progress-detail { color: #8a8278; font-size: 13px; margin-top: 8px; text-align: center; }

.result-section { animation: fadeIn 0.5s ease; }
.result-actions { display: flex; gap: 10px; margin-bottom: 20px; align-items: center; }

.section-title { color: #6b6054; margin: 0 0 14px 0; font-size: 15px; font-weight: 600; }

/* CV 摘要卡片 */
.cv-summary { margin-bottom: 20px; }
.cv-grid { display: flex; gap: 12px; flex-wrap: wrap; }
.cv-card { flex: 1; min-width: 180px; background: #fff; border-radius: 12px; border: 1px solid #e8e2d8; overflow: hidden; }
.cv-card-header { background: #f5f1ec; padding: 8px 14px; font-weight: 600; font-size: 13px; color: #6b7fa0; }
.cv-items { padding: 10px 14px; }
.cv-item { display: flex; align-items: flex-start; padding: 3px 0; font-size: 13px; }
.cv-label { color: #8a8278; width: 36px; flex-shrink: 0; }
.cv-val { color: #4a4238; }
.cv-defects { display: flex; flex-wrap: wrap; gap: 4px; }
.cv-defect-tag { padding: 1px 8px; border-radius: 4px; border: 1px solid; font-size: 12px; }

/* 缺陷图例 */
.legend-bar { display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.legend-item { font-size: 12px; color: #6b6054; display: flex; align-items: center; gap: 4px; }
.legend-dot { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }

/* 标注图 */
.gallery-section { margin-bottom: 20px; }
.gallery-grid { display: flex; gap: 14px; flex-wrap: wrap; }
.gallery-item { text-align: center; }
.gallery-img { max-width: 320px; max-height: 280px; border-radius: 12px; border: 1px solid #e8e2d8; transition: transform 0.2s, box-shadow 0.2s; object-fit: contain; }
.gallery-img:hover { transform: scale(1.02); box-shadow: 0 4px 16px rgba(0,0,0,0.08); }
.gallery-label { color: #8a8278; font-size: 12px; margin-top: 8px; }

/* 报告 */
.report-card { background: #fff; border-radius: 16px; padding: 28px; border: 1px solid #e8e2d8; box-shadow: 0 2px 8px rgba(0,0,0,0.03); }
.report-body { color: #4a4238; font-size: 15px; line-height: 2; }

/* 灯箱 */
.img-lightbox { position: fixed; top: 0; right: 0; bottom: 0; left: 0; background: rgba(0,0,0,0.75); display: flex; align-items: center; justify-content: center; z-index: 9999; cursor: pointer; }
.lightbox-close { position: fixed; top: 20px; right: 24px; color: #fff; font-size: 32px; font-weight: 300; cursor: pointer; z-index: 10000; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.4); border-radius: 50%; }
.lightbox-close:hover { background: rgba(0,0,0,0.6); }
.img-lightbox img { max-width: 85vw; max-height: 85vh; border-radius: 8px; box-shadow: 0 8px 40px rgba(0,0,0,0.4); cursor: default; }

.error-box { color: #c97b7b; margin-top: 14px; padding: 14px; background: #fdf2f2; border-radius: 12px; border: 1px solid #f0d0d0; }

@keyframes fadeIn { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }
</style>
