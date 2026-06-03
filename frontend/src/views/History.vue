<template>
  <div>
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
      <h3 style="color:white;margin:0">历史记录</h3>
      <el-button size="small" @click="load">刷新</el-button>
    </div>

    <el-table :data="records" style="width:100%;background:transparent" @row-click="showDetail" highlight-current-row
      :header-cell-style="{background:'#16213e',color:'#60a5fa',borderColor:'#333'}"
      :row-style="{background:'#16213e',color:'#ccc',borderColor:'#222',cursor:'pointer'}">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column label="报告摘要" show-overflow-tooltip>
        <template #default="{row}">{{ (row.report||'').slice(0,100) }}...</template>
      </el-table-column>
      <el-table-column label="时间" width="170">
        <template #default="{row}">{{ row.created_at?.slice(0,16)?.replace('T',' ') }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{row}">
          <el-button size="small" @click.stop="exportExcel(row.id)">导出 Excel</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" title="巡检报告详情" width="800px" top="5vh">
      <div v-if="detail" style="white-space:pre-wrap;line-height:2;max-height:70vh;overflow-y:auto">
        <el-descriptions :column="2" border style="margin-bottom:16px">
          <el-descriptions-item label="ID">{{ detail.id }}</el-descriptions-item>
          <el-descriptions-item label="时间">{{ detail.created_at?.slice(0,16)?.replace('T',' ') }}</el-descriptions-item>
          <el-descriptions-item label="图片数">{{ detail.image_count || '-' }}</el-descriptions-item>
          <el-descriptions-item label="材质">{{ detail.material || '-' }}</el-descriptions-item>
          <el-descriptions-item label="楼层">{{ detail.floor || '-' }}</el-descriptions-item>
          <el-descriptions-item label="加层">{{ detail.has_extension || '-' }}</el-descriptions-item>
        </el-descriptions>
        <h4>报告正文</h4>
        <div style="color:#333;font-size:14px">{{ detail.report || '无报告' }}</div>
        <h4 v-if="detail.defects?.length">隐患列表 ({{ detail.defects.length }} 条)</h4>
        <el-table v-if="detail.defects?.length" :data="detail.defects" size="small">
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
