<template>
  <div style="display:flex;gap:16px;height:calc(100vh - 100px)">
    <!-- 左侧对话列表 -->
    <div style="width:240px;background:#16213e;border-radius:8px;padding:12px;overflow-y:auto;flex-shrink:0">
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <el-button size="small" @click="newConv" style="flex:1">+ 新建</el-button>
        <el-button size="small" type="danger" @click="delConv" :disabled="!currentId">删除</el-button>
      </div>
      <div v-for="c in conversations" :key="c.id"
        @click="switchConv(c.id)"
        :style="{padding:'8px 10px',cursor:'pointer',borderRadius:'4px',marginBottom:'4px',
          background: c.id===currentId?'#2d2d5e':'transparent',color:'#ccc',fontSize:'13px',
          borderLeft: c.id===currentId?'3px solid #60a5fa':'3px solid transparent'}">
        <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ c.title || '新对话' }}</div>
        <div style="font-size:11px;color:#555;margin-top:2px">{{ c.updated_at?.slice(0,16) }}</div>
      </div>
    </div>

    <!-- 右侧聊天区 -->
    <div style="flex:1;display:flex;flex-direction:column;background:#16213e;border-radius:8px;padding:16px;min-width:0">
      <div style="flex:1;overflow-y:auto;margin-bottom:12px" ref="chatBox">
        <div v-if="!messages.length && !sending" style="text-align:center;color:#555;margin-top:120px;font-size:16px">
          🏗 上传建筑图片 + 输入问题开始巡检
        </div>

        <div v-for="(msg, i) in messages" :key="i" :style="{marginBottom:'16px'}">
          <!-- 用户消息 -->
          <div v-if="msg.role==='user'" style="text-align:right">
            <img v-if="msg.image" :src="msg.image" style="max-width:240px;max-height:200px;border-radius:8px;display:block;margin-left:auto;margin-bottom:4px" />
            <div style="display:inline-block;padding:10px 16px;border-radius:12px 12px 4px 12px;max-width:75%;background:#2d2d5e;color:#ddd;font-size:14px;text-align:left">
              {{ msg.content }}
            </div>
          </div>
          <!-- AI 消息 -->
          <div v-else style="text-align:left">
            <div style="display:inline-block;padding:10px 16px;border-radius:12px 12px 12px 4px;max-width:85%;background:#1a1a2e;color:#ccc;font-size:14px;line-height:1.7;text-align:left">
              <div v-if="msg.html" v-html="msg.html"></div>
              <div v-else style="white-space:pre-wrap">{{ msg.content }}</div>
            </div>
          </div>
        </div>

        <!-- 实时 CoT 面板 -->
        <CoTPanel :steps="streamSteps" v-if="streamSteps.length" />
        <div v-if="sending" style="color:#f59e0b;font-size:13px;padding:8px">
          <span class="dot-pulse">🧠 Manager Agent 思考中</span>
        </div>
      </div>

      <!-- 输入区 -->
      <div style="display:flex;gap:8px;align-items:flex-end">
        <input type="file" ref="fileInput" accept="image/*" style="display:none" @change="onFileChange" />
        <el-button size="small" @click="$refs.fileInput.click()" :type="imgPreview ? 'primary' : 'default'" style="flex-shrink:0">
          <el-icon><Picture /></el-icon>
          {{ imgPreview ? '✓ 已选图' : '' }}
        </el-button>
        <el-input v-model="input" placeholder="输入问题，例如：全面检测这栋楼..."
          @keyup.enter="send" :disabled="sending" style="flex:1" />
        <el-button type="primary" @click="send" :loading="sending" style="flex-shrink:0">发送</el-button>
      </div>
      <img v-if="imgPreview" :src="imgPreview" style="height:60px;border-radius:4px;margin-top:4px" />
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { chatAPI } from '../api/chat'
import CoTPanel from '../components/CoTPanel.vue'

const conversations = ref([])
const currentId = ref(null)
const messages = ref([])
const input = ref('')
const sending = ref(false)
const streamSteps = ref([])
const imgFile = ref(null)
const imgPreview = ref(null)
const chatBox = ref(null)

onMounted(async () => {
  try { conversations.value = await chatAPI.listConversations() } catch(e) {}
})

async function newConv() {
  currentId.value = null; messages.value = []; streamSteps.value = []
}
async function switchConv(id) {
  currentId.value = id; streamSteps.value = []
  try {
    const data = await chatAPI.getConversation(id)
    messages.value = data.messages.map(m => {
      const meta = m.metadata || {}
      return {
        role: m.role,
        content: m.content || '',
        html: m.role === 'assistant' && /<img|<div|<pre/i.test(m.content || '') ? m.content : null,
        image: meta.has_image && m.images?.length ? '/api/chat/images/' + m.id : null,
      }
    })
  } catch(e) { console.error(e) }
  await nextTick(); scrollBottom()
}
async function delConv() {
  if (!currentId.value) return
  await chatAPI.deleteConversation(currentId.value)
  conversations.value = conversations.value.filter(c => c.id !== currentId.value)
  newConv()
}
function onFileChange(e) {
  const f = e.target.files[0]
  if (f) { imgFile.value = f; imgPreview.value = URL.createObjectURL(f) }
}
async function send() {
  const msg = input.value.trim(); if (!msg) return
  input.value = ''; sending.value = true; streamSteps.value = []

  messages.value.push({ role: 'user', content: msg, image: imgPreview.value })
  await nextTick(); scrollBottom()

  // 添加占位消息用于流式更新
  const aiIdx = messages.value.length
  messages.value.push({ role: 'assistant', content: '思考中...' })

  chatAPI.sendStream(
    msg, currentId.value,
    (step) => {
      // 实时收到 CoT 步骤
      streamSteps.value = [...streamSteps.value, step]
      scrollBottom()
    },
    (result) => {
      // Agent 完成
      currentId.value = result.conversation_id
      messages.value[aiIdx] = {
        role: 'assistant',
        content: result.response,
        html: /<img|<div|<pre/i.test(result.response || '') ? result.response : null,
      }
      sending.value = false
      chatAPI.listConversations().then(c => conversations.value = c)
      nextTick(() => scrollBottom())
    },
    (err) => {
      messages.value[aiIdx] = { role: 'assistant', content: '出错了: ' + err.message }
      sending.value = false
    }
  )

  imgFile.value = null; imgPreview.value = null
}
function scrollBottom() {
  if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
}
</script>

<style scoped>
.dot-pulse::after { content: ''; animation: dots 1.5s steps(4,end) infinite; }
@keyframes dots { 0%{content:''} 25%{content:'.'} 50%{content:'..'} 75%{content:'...'} 100%{content:''} }
</style>
