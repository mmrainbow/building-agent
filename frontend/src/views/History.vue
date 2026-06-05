<template>
  <div class="history-page">
    <div class="history-header">
      <h3 class="history-title">历史记录</h3>
      <el-button size="small" @click="load" class="refresh-btn">刷新</el-button>
    </div>

    <el-table :data="records" @row-click="showDetail" highlight-current-row class="history-table">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column label="报告摘要" show-overflow-tooltip>
        <template #default="{row}">{{ (row.report||'').slice(0,100) }}...</template>
      </el-table-column>
      <el-table-column label="时间" width="170">
        <template #default="{row}">{{ row.created_at?.slice(0,16)?.replace('T',' ') }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{row}">
          <el-button size="small" @click.stop="exportExcel(row.id)" class="export-btn">导出 Excel</el-button>
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
import { ref } from 'vue'
import { historyAPI } from '../api/history'
import client from '../api/index'

const records = ref([])
const dialog = ref(false)
const detail = ref(null)

async function load() {
  try { const r = await client.get('/history'); records.value = r.data } catch(e) {}
}
async function showDetail(row) {
  try { const r = await client.get(`/history/${row.id}`); detail.value = r.data; dialog.value = true } catch(e) {}
}
async function exportExcel(id) {
  try { await historyAPI.exportExcel(id) } catch(e) {}
}
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
.defect-table { border-radius: 8px; overflow: hidden; }
</style>
