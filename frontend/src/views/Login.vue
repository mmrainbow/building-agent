<template>
  <div class="login-page">
    <div class="login-bg-shape"></div>
    <div class="login-bg-shape2"></div>
    <el-card class="login-card">
      <template #header>
        <h2 class="login-title">登录 Building Agent</h2>
      </template>
      <el-form>
        <el-form-item><el-input v-model="username" placeholder="用户名" prefix-icon="User" size="large" /></el-form-item>
        <el-form-item><el-input v-model="password" type="password" placeholder="密码" prefix-icon="Lock" size="large" @keyup.enter="handleLogin" /></el-form-item>
        <el-form-item>
          <el-button type="primary" class="login-btn" @click="handleLogin" :loading="loading" size="large">登 录</el-button>
        </el-form-item>
        <el-form-item>
          <el-button text class="toggle-btn" @click="showReg = !showReg">{{ showReg ? '返回登录' : '注册新账号' }}</el-button>
        </el-form-item>
        <template v-if="showReg">
          <el-form-item><el-input v-model="regPass2" type="password" placeholder="确认密码" size="large" /></el-form-item>
          <el-form-item>
            <el-button class="reg-btn" @click="handleRegister" :loading="loading" size="large">注 册</el-button>
          </el-form-item>
        </template>
        <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="login-error" />
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
const router = useRouter()
const auth = useAuthStore()
const username = ref('')
const password = ref('')
const regPass2 = ref('')
const showReg = ref(false)
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  loading.value = true; error.value = ''
  try { await auth.login(username.value, password.value); router.push('/chat') }
  catch (e) { error.value = e.response?.data?.detail || '登录失败' }
  finally { loading.value = false }
}
async function handleRegister() {
  if (password.value !== regPass2.value) { error.value = '两次密码不一致'; return }
  loading.value = true; error.value = ''
  try { await auth.register(username.value, password.value); showReg.value = false; error.value = '注册成功，请登录' }
  catch (e) { error.value = e.response?.data?.detail || '注册失败' }
  finally { loading.value = false }
}
</script>

<style scoped>
.login-page {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  background: linear-gradient(160deg, #f0ebe3 0%, #f5f1ec 40%, #faf8f4 70%, #ede7df 100%);
  position: relative;
  overflow: hidden;
}
.login-bg-shape {
  position: absolute;
  top: -20%;
  right: -10%;
  width: 500px;
  height: 500px;
  border-radius: 40% 60% 60% 40% / 30% 30% 70% 70%;
  background: radial-gradient(circle, rgba(139,158,201,0.12) 0%, transparent 70%);
  pointer-events: none;
}
.login-bg-shape2 {
  position: absolute;
  bottom: -15%;
  left: -8%;
  width: 400px;
  height: 400px;
  border-radius: 50% 40% 60% 45% / 55% 45% 55% 45%;
  background: radial-gradient(circle, rgba(180,160,140,0.10) 0%, transparent 70%);
  pointer-events: none;
}
.login-card {
  width: 420px;
  background: #fff;
  border: 1px solid #e8e2d8;
  border-radius: 16px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.06), 0 12px 60px rgba(0,0,0,0.04);
  z-index: 1;
}
.login-card :deep(.el-card__header) {
  border-bottom: 1px solid #f0ebe3;
  padding: 28px 24px 18px;
}
.login-card :deep(.el-card__body) {
  padding: 20px 28px 30px;
}
.login-title {
  text-align: center;
  color: #4a4238;
  margin: 0;
  font-weight: 600;
  font-size: 20px;
}
.login-btn {
  width: 100%;
  --el-button-bg-color: #6b7fa0;
  --el-button-border-color: #6b7fa0;
  --el-button-hover-bg-color: #7d90b0;
  --el-button-hover-border-color: #7d90b0;
}
.reg-btn {
  width: 100%;
  --el-button-bg-color: #f3efe9;
  --el-button-border-color: #e0d9ce;
  --el-button-text-color: #6b6054;
}
.toggle-btn { width: 100%; color: #8a8278; }
.login-error {
  margin-top: 8px;
  --el-alert-bg-color: #fdf2f2;
  border-radius: 10px;
}
</style>
