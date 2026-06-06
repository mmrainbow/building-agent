<template>
  <div class="history-page">
    <div class="history-header">
      <h3 class="history-title">历史记录</h3>
      <el-button size="small" @click="load" :loading="loading" class="refresh-btn">刷新</el-button>
    </div>

    <el-table
      :data="records"
      :loading="loading"
      @row-click="showDetail"
      highlight-current-row
      class="history-table"
    >
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column label="报告摘要" show-overflow-tooltip>
        <template #default="{row}">{{ (row.report||'').slice(0,100) }}...</template>
      </el-table-column>
      <el-table-column label="时间" width="170">
        <template #default="{row}">{{ row.created_at?.slice(0,16)?.replace('T',' ') }}</template>
      </el-table-column>
      <el-table-column label="操作" width="170">
        <template #default="{row}">
          <el-dropdown @command="(format) => exportFile(row.id, format)" @click.stop>
            <el-button size="small" class="export-btn">导出报告</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="xlsx">Excel</el-dropdown-item>
                <el-dropdown-item command="docx">Word</el-dropdown-item>
                <el-dropdown-item command="md">Markdown</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" title="巡检报告详情" width="800px" top="5vh" class="detail-dialog">
      <div v-if="detail" class="detail-body">
        <el-descriptions :column="2" border class="detail-desc">
          <el-descriptions-item label="ID">{{ detail.id }}</el-descriptions-item>
          <el-descriptions-item label="时间">{{ detail.created_at?.slice(0,16)?.replace('T',' ') }}</el-descriptions-item>
          <el-descriptions-item label="图片数">{{ detail.image_count || '-' }}</el-descriptions-item>
          <el-descriptions-item label="材质">{{ detail.material || '-' }}</el-descriptions-item>
          <el-descriptions-item label="楼层">{{ detail.floor || '-' }}</el-descriptions-item>
          <el-descriptions-item label="加层">{{ detail.has_extension || '-' }}</el-descriptions-item>
        </el-descriptions>
        <h4 class="detail-subtitle">报告正文</h4>
        <div class="detail-report">{{ detail.report || '无报告' }}</div>
        <h4 v-if="detail.images?.length" class="detail-subtitle">图片预览</h4>
        <div v-if="detail.images?.length" class="image-grid">
          <div v-for="img in detail.images" :key="img.id" class="image-card">
            <div class="image-title">{{ img.name }}</div>
            <div class="image-pair">
              <div>
                <div class="image-label">原图</div>
                <img :src="withToken(img.original_url)" class="preview-img" />
              </div>
              <div>
                <div class="image-label">标注图</div>
                <img :src="withToken(img.annotated_url)" class="preview-img" />
              </div>
            </div>
            <div class="image-meta">
              材质：{{ img.material || '未知' }} ｜ 楼层：{{ img.floor || '未知' }} ｜ 加层：{{ img.has_extension || '未知' }}
            </div>
          </div>
        </div>
        <h4 v-if="detail.defects?.length" class="detail-subtitle">隐患列表 ({{ detail.defects.length }} 条)</h4>
        <el-table v-if="detail.defects?.length" :data="detail.defects" size="small" class="defect-table">
          <el-table-column prop="type" label="类型" width="100" />
          <el-table-column prop="area" label="面积(px²)" width="120" />
          <el-table-column prop="image_id" label="图片ID" width="80" />
        </el-table>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { historyAPI } from '../api/history'
import client from '../api/index'

const records = ref([])
const dialog = ref(false)
const detail = ref(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const r = await client.get('/history')
    records.value = r.data
  } catch(e) {
    ElMessage.error('巡检记录加载失败，请稍后重试')
  } finally {
    loading.value = false
  }
}
async function showDetail(row) {
  try {
    const r = await client.get(`/history/${row.id}`)
    detail.value = r.data
    dialog.value = true
  } catch(e) {
    ElMessage.error('巡检详情加载失败，请刷新后重试')
  }
}
function withToken(url) {
  const token = localStorage.getItem('token')
  return token ? `${url}?token=${encodeURIComponent(token)}` : url
}
async function exportFile(id, format) {
  try { await historyAPI.exportFile(id, format) } catch(e) { ElMessage.error('导出失败') }
}

onMounted(load)
</script>

<style scoped>
.history-page { color: #4a4238; }
.history-header { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; }
.history-title { color: #4a4238; margin: 0; font-size: 18px; }
.refresh-btn {
  --el-button-bg-color: #f3efe9;
  --el-button-border-color: #e0d9ce;
  --el-button-text-color: #6b6054;
}
.export-btn {
  --el-button-bg-color: #f5f1ec;
  --el-button-border-color: #e0d9ce;
  --el-button-text-color: #6b6054;
}

.history-table {
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.03);
}

.detail-body {
  white-space: pre-wrap;
  line-height: 2;
  max-height: 70vh;
  overflow-y: auto;
  color: #4a4238;
}
.detail-desc { margin-bottom: 16px; }
.detail-subtitle { color: #6b6054; margin: 18px 0 10px; }
.detail-report {
  color: #4a4238;
  font-size: 14px;
  background: #faf8f4;
  padding: 18px;
  border-radius: 10px;
  border: 1px solid #e8e2d8;
}
.image-grid { display: flex; flex-direction: column; gap: 14px; }
.image-card {
  background: #fff;
  border: 1px solid #e8e2d8;
  border-radius: 10px;
  padding: 12px;
}
.image-title { font-weight: 600; color: #6b6054; margin-bottom: 8px; }
.image-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.image-label { color: #8a8278; font-size: 12px; margin-bottom: 4px; }
.preview-img {
  width: 100%;
  max-height: 260px;
  object-fit: contain;
  border-radius: 8px;
  background: #faf8f4;
  border: 1px solid #eee5db;
}
.image-meta { margin-top: 8px; color: #8a8278; font-size: 12px; }
.defect-table { border-radius: 8px; overflow: hidden; }
</style>
