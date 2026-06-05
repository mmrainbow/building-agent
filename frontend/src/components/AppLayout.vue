<template>
  <el-container class="app-layout">
    <el-header class="app-header">
      <span class="app-logo">🏗 Building Agent</span>
      <span class="header-right">
        <span class="username">{{ auth.username }}</span>
        <el-button size="small" @click="handleLogout" class="logout-btn">退出</el-button>
      </span>
    </el-header>
    <el-container>
      <el-aside width="200px" class="app-sidebar">
        <el-menu router :default-active="route.path" class="side-menu">
          <el-menu-item index="/chat"><el-icon><ChatDotSquare /></el-icon> 智能问答</el-menu-item>
          <el-menu-item index="/inspection"><el-icon><Picture /></el-icon> 图像巡检</el-menu-item>
          <el-menu-item index="/history"><el-icon><Document /></el-icon> 历史记录</el-menu-item>
          <el-menu-item index="/monitor"><el-icon><Monitor /></el-icon> Agent 监控</el-menu-item>
        </el-menu>
      </el-aside>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
function handleLogout() { auth.logout(); router.push('/login') }
</script>

<style>
body {
  margin: 0;
  font-family: 'Microsoft YaHei', 'PingFang SC', -apple-system, sans-serif;
  background: #f3efe9;
  color: #4a4238;
}

/* ── 布局 ── */
.app-layout { height: 100vh; }

.app-header {
  background: #fff;
  color: #4a4238;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  border-bottom: 1px solid #e8e2d8;
  box-shadow: 0 1px 6px rgba(0,0,0,0.04);
}
.app-logo { font-size: 18px; font-weight: 600; letter-spacing: 0.5px; }
.header-right { display: flex; align-items: center; gap: 12px; }
.username { color: #8a8278; font-size: 14px; }
.logout-btn {
  --el-button-bg-color: #f3efe9;
  --el-button-border-color: #e0d9ce;
  --el-button-text-color: #6b6054;
}

.app-sidebar {
  background: #faf8f4;
  border-right: 1px solid #e8e2d8;
}
.side-menu {
  border: none;
  --el-menu-bg-color: #faf8f4;
  --el-menu-text-color: #8a8278;
  --el-menu-active-color: #6b7fa0;
  --el-menu-hover-bg-color: #f0ebe3;
}
.side-menu .el-menu-item {
  font-size: 14px;
  margin: 2px 8px;
  border-radius: 8px;
  transition: all 0.2s ease;
}

.app-main {
  background: #f3efe9;
  padding: 24px;
}

/* ── 滚动条 ── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #d5cdc4; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #b8aea4; }

/* ── Element Plus 全局覆盖 ── */
.el-table {
  --el-table-bg-color: #fff;
  --el-table-tr-bg-color: #fff;
  --el-table-header-bg-color: #faf8f4;
  --el-table-text-color: #4a4238;
  --el-table-border-color: #e8e2d8;
  --el-table-row-hover-bg-color: #f5f0ea;
  --el-table-header-text-color: #6b7fa0;
}
.el-dialog {
  --el-dialog-bg-color: #fff;
  --el-dialog-title-color: #4a4238;
}
.el-descriptions {
  --el-descriptions-item-bordered-label-background: #faf8f4;
}
.el-card {
  --el-card-bg-color: #fff;
  --el-card-border-color: #e8e2d8;
}
.el-input__wrapper {
  --el-input-bg-color: #faf8f4;
  --el-input-border-color: #e0d9ce;
  box-shadow: none !important;
}
.el-input__inner { color: #4a4238; }
.el-input__inner::placeholder { color: #b0a89e; }
.el-button--default {
  --el-button-bg-color: #f3efe9;
  --el-button-border-color: #e0d9ce;
  --el-button-text-color: #6b6054;
}
.el-button--default:hover {
  --el-button-bg-color: #ebe4da;
}
.el-tag {
  --el-tag-bg-color: #f3efe9;
  --el-tag-border-color: #e0d9ce;
  --el-tag-text-color: #6b6054;
}
</style>
