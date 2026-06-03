<template>
  <div style="display:flex;justify-content:center;align-items:center;height:100vh;background:linear-gradient(135deg,#0f0f1a,#1a1a2e)">
    <el-card style="width:420px;background:#16213e;border:1px solid #2d2d5e">
      <template #header>
        <h2 style="text-align:center;color:white;margin:0">登录 Building Agent</h2>
      </template>
      <el-form>
        <el-form-item><el-input v-model="username" placeholder="用户名" prefix-icon="User" /></el-form-item>
        <el-form-item><el-input v-model="password" type="password" placeholder="密码" prefix-icon="Lock" @keyup.enter="handleLogin" /></el-form-item>
        <el-form-item>
          <el-button type="primary" style="width:100%" @click="handleLogin" :loading="loading">登 录</el-button>
        </el-form-item>
        <el-form-item>
          <el-button text style="width:100%;color:#888" @click="showReg = !showReg">{{ showReg ? '返回登录' : '注册新账号' }}</el-button>
        </el-form-item>
        <template v-if="showReg">
          <el-form-item><el-input v-model="regPass2" type="password" placeholder="确认密码" /></el-form-item>
          <el-form-item>
            <el-button style="width:100%" @click="handleRegister" :loading="loading">注 册</el-button>
          </el-form-item>
        </template>
        <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
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
