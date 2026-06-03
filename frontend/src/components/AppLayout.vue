<template>
  <el-container style="height:100vh">
    <el-header style="background:#1a1a2e;color:white;display:flex;align-items:center;justify-content:space-between;padding:0 20px">
      <span style="font-size:18px;font-weight:bold">🏗 Building Agent</span>
      <span>
        <span style="color:#a78bfa;margin-right:12px">{{ auth.username }}</span>
        <el-button size="small" @click="handleLogout">退出</el-button>
      </span>
    </el-header>
    <el-container>
      <el-aside width="200px" style="background:#16213e">
        <el-menu router :default-active="route.path" background-color="#16213e" text-color="#a0aec0" active-text-color="#60a5fa" style="border:none">
          <el-menu-item index="/chat"><el-icon><ChatDotSquare /></el-icon> 智能问答</el-menu-item>
          <el-menu-item index="/inspection"><el-icon><Picture /></el-icon> 图像巡检</el-menu-item>
          <el-menu-item index="/history"><el-icon><Document /></el-icon> 历史记录</el-menu-item>
          <el-menu-item index="/monitor"><el-icon><Monitor /></el-icon> Agent 监控</el-menu-item>
        </el-menu>
      </el-aside>
      <el-main style="background:#0f0f1a;padding:20px">
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
body { margin:0; font-family:'Microsoft YaHei', sans-serif; }
.el-menu-item { font-size:14px; }
</style>
