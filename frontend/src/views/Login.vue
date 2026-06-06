<template>
  <div class="login-page">
    <div class="login-bg-shape"></div>
    <div class="login-bg-shape2"></div>
    <el-card class="login-card">
      <template #header>
        <h2 class="login-title">{{ pageTitle }}</h2>
        <p v-if="adminMode" class="login-subtitle">管理端入口，仅限管理员账号</p>
      </template>
      <el-form>
        <el-form-item><el-input v-model="username" placeholder="用户名" prefix-icon="User" size="large" /></el-form-item>
        <el-form-item><el-input v-model="password" type="password" placeholder="密码" prefix-icon="Lock" size="large" @keyup.enter="handleLogin" /></el-form-item>
        <template v-if="showReg">
          <el-form-item><el-input v-model="regPass2" type="password" placeholder="确认密码" size="large" @keyup.enter="handleRegister" /></el-form-item>
        </template>
        <el-form-item>
          <el-button
            v-if="!showReg"
            type="primary"
            class="login-btn"
            @click="handleLogin"
            :loading="loading"
            size="large"
          >
            {{ adminMode ? '管理员登录' : '登 录' }}
          </el-button>
          <el-button
            v-else
            type="primary"
            class="login-btn"
            @click="handleRegister"
            :loading="loading"
            size="large"
          >
            注 册
          </el-button>
        </el-form-item>
        <el-form-item v-if="!adminMode">
          <el-button text class="toggle-btn" @click="toggleRegister">
            {{ showReg ? '返回登录' : '注册新账号' }}
          </el-button>
        </el-form-item>
        <el-alert
          v-if="message"
          :title="message"
          :type="messageType"
          show-icon
          :closable="false"
          class="login-message"
        />
      </el-form>
      <button class="admin-entry" @click="toggleAdminMode">
        {{ adminMode ? '返回普通登录' : '管理入口' }}
      </button>
    </el-card>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
const router = useRouter()
const auth = useAuthStore()
const username = ref('')
const password = ref('')
const regPass2 = ref('')
const showReg = ref(false)
const adminMode = ref(false)
const loading = ref(false)
const message = ref('')
const messageType = ref('error')

const pageTitle = computed(() => {
  if (adminMode.value) return '管理员登录'
  return showReg.value ? '注册 Building Agent' : '登录 Building Agent'
})

function setMessage(text, type = 'error') {
  message.value = text
  messageType.value = type
}

function clearMessage() {
  message.value = ''
}

function toggleRegister() {
  showReg.value = !showReg.value
  regPass2.value = ''
  clearMessage()
}

function toggleAdminMode() {
  adminMode.value = !adminMode.value
  showReg.value = false
  regPass2.value = ''
  clearMessage()
}

async function handleLogin() {
  loading.value = true; clearMessage()
  try {
    await auth.login(username.value, password.value)
    if (adminMode.value && !auth.isAdmin) {
      auth.logout()
      setMessage('该账号不是管理员账号，请返回普通登录')
      return
    }
    router.push(adminMode.value ? '/feedback' : '/chat')
  }
  catch (e) { setMessage(e.response?.data?.detail || '登录失败') }
  finally { loading.value = false }
}
async function handleRegister() {
  if (password.value !== regPass2.value) { setMessage('两次密码不一致'); return }
  loading.value = true; clearMessage()
  try {
    await auth.register(username.value, password.value)
    showReg.value = false
    password.value = ''
    regPass2.value = ''
    setMessage('注册成功，请登录', 'success')
  }
  catch (e) { setMessage(e.response?.data?.detail || '注册失败') }
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
  position: relative;
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
.login-subtitle {
  text-align: center;
  color: #a08f80;
  margin: 8px 0 0;
  font-size: 12px;
}
.login-btn {
  width: 100%;
  --el-button-bg-color: #6b7fa0;
  --el-button-border-color: #6b7fa0;
  --el-button-hover-bg-color: #7d90b0;
  --el-button-hover-border-color: #7d90b0;
}
.toggle-btn { width: 100%; color: #8a8278; }
.login-message {
  margin-top: 8px;
  border-radius: 10px;
}
.admin-entry {
  position: absolute;
  right: 14px;
  bottom: 10px;
  border: none;
  background: transparent;
  color: #d0c6bb;
  font-size: 11px;
  cursor: pointer;
  opacity: 0.55;
}
.admin-entry:hover {
  color: #8b9ec9;
  opacity: 1;
}
</style>
