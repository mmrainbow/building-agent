<template>
  <div class="chat-page">
    <!-- 左侧对话列表 -->
    <div class="conv-sidebar">
      <div class="conv-actions">
        <el-button size="small" @click="newConv" class="new-btn">+ 新建</el-button>
        <el-button size="small" type="danger" @click="delConv" :disabled="!currentId" class="del-btn">删除</el-button>
        <el-button size="small" @click="showMemories = true; fetchMemories()" :disabled="!currentId" class="mem-btn" title="Memory">🧠</el-button>
      </div>
      <div v-for="c in conversations" :key="c.id"
        @click="switchConv(c.id)"
        class="conv-item" :class="{ active: c.id === currentId }">
        <div class="conv-title">{{ c.title || '新对话' }}</div>
        <div class="conv-time">{{ c.updated_at?.slice(0,16) }}</div>
      </div>
    </div>

    <!-- 右侧聊天区 -->
    <div class="chat-main">
      <!-- Agent 状态条 -->
      <div class="agent-bar" v-if="agentStatus">
        <span class="agent-dot" :class="agentStatus.manager?.status"></span> 🤖 Manager
        <span class="agent-sep">|</span>
        <span class="agent-dot" :class="agentStatus.report?.status"></span> 🤖 Report
        <span class="agent-sep">|</span>
        <svg class="mem-ring" width="16" height="16" viewBox="0 0 16 16">
          <circle cx="8" cy="8" r="6" fill="none" stroke="#e8e2d8" stroke-width="2"/>
          <circle cx="8" cy="8" r="6" fill="none" :stroke="memColor" stroke-width="2"
            :stroke-dasharray="memDasharray" stroke-dashoffset="9.4" stroke-linecap="round"
            transform="rotate(-90 8 8)"/>
        </svg>
        Memory {{ agentStatus.memory?.pct || 0 }}%
      </div>
      <div class="chat-messages" ref="chatBox" @click="onChatClick">
        <div v-if="!messages.length && !sending" class="chat-placeholder">
          🏗 上传建筑图片 + 输入问题开始巡检
        </div>

        <div v-for="msg in messages" :key="msg.id || msg.content" class="msg-row">
          <div v-if="msg.role==='user'" class="msg-user-wrap">
            <div v-if="msg.images?.length" class="msg-img-row">
              <img v-for="(url, i) in msg.images" :key="i" :src="url" class="msg-img" />
            </div>
            <div class="msg-bubble user-bubble">{{ msg.content }}</div>
          </div>
          <div v-else class="msg-ai-wrap">
            <div class="msg-bubble ai-bubble">
              <div v-if="msg.html" v-html="msg.html"></div>
              <div v-else class="msg-text">{{ msg.content }}</div>
            </div>
            <div v-if="msg.id" class="feedback-row">
              <span class="feedback-label">本次回答有帮助吗？</span>
              <el-rate
                v-model="msg.feedbackRating"
                size="small"
                :max="5"
                :disabled="msg.feedbackSubmitting"
                @change="submitFeedback(msg)"
              />
              <el-button size="small" text @click="openFeedbackDialog(msg)">补充意见</el-button>
              <span v-if="msg.feedbackSubmitted" class="feedback-done">已反馈</span>
            </div>
            <CoTPanel :steps="msg._cotSteps" v-if="msg._cotSteps?.length" :defaultExpanded="false" class="msg-cot" />
          </div>
        </div>

        <CoTPanel :steps="streamSteps" v-if="streamSteps.length" />
        <div v-if="sending && !streamSteps.length" class="thinking-hint">
          <span class="dot-pulse">🧠 Manager Agent 思考中</span>
        </div>
      </div>

      <!-- 多图预览 — 输入框上方靠右 -->
      <div class="preview-row" v-if="imgPreviews.length">
        <div class="preview-wrap" v-for="(url, i) in imgPreviews" :key="i">
          <img :src="url" class="img-preview" />
          <span class="preview-badge">图{{ i+1 }}</span>
          <span class="preview-remove" @click="removeImg(i)">✕</span>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="chat-input-row">
        <input type="file" ref="fileInput" accept="image/*" multiple class="file-hidden" @change="onFileChange" />
        <el-button size="small" @click="$refs.fileInput.click()" :type="imgPreviews.length ? 'primary' : 'default'" class="img-btn">
          <el-icon><Picture /></el-icon>
          {{ imgPreviews.length ? `✓ ${imgPreviews.length}图` : '' }}
        </el-button>
        <el-input v-model="input" placeholder="输入问题，例如：全面检测这栋楼..."
          @keyup.enter="send" :disabled="sending" class="msg-input" size="large" />
        <el-button type="primary" @click="send" :loading="sending" class="send-btn" size="large">发送</el-button>
      </div>
    </div>

    <!-- Memory 抽屉 -->
    <el-drawer v-model="showMemories" title="对话记忆" size="360px" direction="rtl">
      <div v-if="!memories.length" class="mem-empty">暂无长期记忆</div>
      <div v-for="m in memories" :key="m.id" class="mem-item">
        <div class="mem-header">
          <el-tag size="small" :type="m.memory_type==='insight'?'warning':m.memory_type==='preference'?'primary':'info'">
            {{ m.memory_type }}
          </el-tag>
          <span class="mem-imp">{{ '★'.repeat(Math.round((m.importance||5)/2)) }}</span>
          <el-button size="small" text @click="delMemory(m.id)" class="mem-del">×</el-button>
        </div>
        <div class="mem-content">{{ m.content }}</div>
      </div>
    </el-drawer>

    <!-- 图片灯箱 -->
    <ImgLightbox ref="lightbox" />

    <el-dialog v-model="feedbackDialog.visible" title="补充反馈意见" width="420px">
      <el-form label-position="top">
        <el-form-item label="评分">
          <el-rate v-model="feedbackDialog.rating" />
        </el-form-item>
        <el-form-item label="意见或修改建议">
          <el-input
            v-model="feedbackDialog.comment"
            type="textarea"
            :rows="4"
            maxlength="1000"
            show-word-limit
            placeholder="例如：回答过于笼统、缺少处置建议、隐患判断不准确..."
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="feedbackDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="feedbackDialog.submitting" @click="submitFeedbackDialog">提交反馈</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref, nextTick, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { chatAPI } from '../api/chat'
import client from '../api/index'
import CoTPanel from '../components/CoTPanel.vue'
import ImgLightbox from '../components/ImgLightbox.vue'
import { renderMarkdown, isHtmlContent } from '../utils/markdown'

const conversations = ref([])
const currentId = ref(null)
const messages = ref([])
const input = ref('')
const sending = ref(false)
const streamSteps = ref([])
const imgFiles = ref([])
const imgPreviews = ref([])
const chatBox = ref(null)
const lightbox = ref(null)
const feedbackDialog = ref({
  visible: false,
  message: null,
  rating: 5,
  comment: '',
  submitting: false,
})

function onChatClick(e) {
  if (e.target.tagName === 'IMG' && e.target.src.startsWith('data:image')) {
    lightbox.value?.show(e.target.src)
  }
}

const agentStatus = ref(null)
const memColor = computed(() => {
  const pct = agentStatus.value?.memory?.pct || 0
  return pct > 80 ? '#c97b7b' : pct > 50 ? '#d4a574' : '#7eb89e'
})
const memDasharray = computed(() => {
  const pct = agentStatus.value?.memory?.pct || 0
  const len = 2 * Math.PI * 6  // 圆环周长
  const filled = (pct / 100) * len
  return `${filled} ${len - filled}`
})
const showMemories = ref(false)
const memories = ref([])
async function fetchMemories() {
  if (!currentId.value) return
  try { const r = await client.get('/chat/memories', { params: { conversation_id: currentId.value } }); memories.value = r.data } catch(e) {}
}
async function delMemory(id) {
  try { await client.delete(`/chat/memories/${id}`); memories.value = memories.value.filter(m => m.id !== id) } catch(e) {}
}

async function fetchAgentStatus() {
  if (!currentId.value) {
    agentStatus.value = { manager: { status: 'online' }, report: { status: 'online' }, memory: { pct: 0, threshold: 60000, total_chars: 0 } }
    return
  }
  try { const r = await client.get('/agent/status', { params: { conversation_id: currentId.value } }); agentStatus.value = r.data } catch(e) {}
}

onMounted(async () => {
  try { conversations.value = await chatAPI.listConversations() } catch(e) {}
  fetchAgentStatus()
})

async function newConv() {
  currentId.value = null; messages.value = []; streamSteps.value = []; fetchAgentStatus()
}
async function switchConv(id) {
  currentId.value = id; streamSteps.value = []; fetchAgentStatus()
  try {
    const data = await chatAPI.getConversation(id)
    const msgs = []
    for (const m of data.messages) {
      const meta = m.metadata || {}
      // 从 metadata 恢复标注图（切换对话时图片不丢）
      let aiHtml = m.role === 'assistant' && (isHtmlContent(m.content) || meta.annotated_images?.length)
        ? (meta.annotated_images || []).join('') + renderMarkdown(m.content || '')
        : null
      const msg = {
        id: m.id,
        role: m.role,
        content: m.content || '',
        html: aiHtml,
        images: meta.has_image && meta.image_count > 0
          ? Array.from({length: meta.image_count}, (_, i) => `/api/chat/images/${m.id}?idx=${i}`)
          : null,
        toolCalls: meta.tool_calls || null,
        feedbackRating: m.feedback?.rating || null,
        feedbackSubmitted: !!m.feedback,
        feedbackSubmitting: false,
      }
      msgs.push(msg)
      // 从 assistant 消息的 metadata 提取 CoT
      if (m.role === 'assistant' && meta.tool_calls?.length) {
        const steps = []
        for (const tc of meta.tool_calls) {
          steps.push({
            type: 'tool',
            name: tc.name,
            status: 'done',
            elapsed_ms: tc.elapsed_ms || 0,
          })
        }
        msg._cotSteps = steps
      }
    }
    messages.value = msgs
  } catch(e) { console.error(e) }
  await nextTick(); scrollBottom()
}
async function delConv() {
  if (!currentId.value) return
  await chatAPI.deleteConversation(currentId.value)
  conversations.value = conversations.value.filter(c => c.id !== currentId.value)
  newConv()
}
// 将 Markdown 图片语法转为 HTML img 标签，同时清理模型幻觉产生的无效 base64
function onFileChange(e) {
  for (const f of e.target.files) {
    if (f.type.startsWith('image/')) {
      imgFiles.value.push(f)
      imgPreviews.value.push(URL.createObjectURL(f))
    }
  }
  e.target.value = ''
}
function removeImg(i) {
  imgFiles.value.splice(i, 1)
  imgPreviews.value.splice(i, 1)
}
async function send() {
  const msg = input.value.trim(); if (!msg) return
  input.value = ''; sending.value = true; streamSteps.value = []

  // 保存当前图片并清空输入态
  const files = [...imgFiles.value]
  const previews = [...imgPreviews.value]
  imgFiles.value = []
  imgPreviews.value = []

  messages.value.push({ role: 'user', content: msg, images: previews })
  await nextTick(); scrollBottom()

  const aiIdx = messages.value.length
  messages.value.push({ role: 'assistant', content: '思考中...' })

  chatAPI.sendStream(
    msg, currentId.value, files.length ? files : null,
    (step) => {
      streamSteps.value = [...streamSteps.value, step]
      scrollBottom()
    },
    (result) => {
      currentId.value = result.conversation_id
      messages.value[aiIdx] = {
        id: result.message_id,
        role: 'assistant',
        content: result.response,
        html: isHtmlContent(result.response) ? renderMarkdown(result.response) : null,
        feedbackRating: null,
        feedbackSubmitted: false,
        feedbackSubmitting: false,
      }
      sending.value = false
      chatAPI.listConversations().then(c => conversations.value = c)
      fetchAgentStatus()
      if (showMemories.value) fetchMemories()
      nextTick(() => scrollBottom())
    },
    (err) => {
      messages.value[aiIdx] = { role: 'assistant', content: '出错了: ' + err.message }
      sending.value = false
    }
  )
}
function scrollBottom() {
  if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
}

async function submitFeedback(msg, comment = null) {
  if (!msg?.id || !msg.feedbackRating) return
  msg.feedbackSubmitting = true
  try {
    await chatAPI.submitFeedback(msg.id, msg.feedbackRating, comment)
    msg.feedbackSubmitted = true
    ElMessage.success('反馈已记录，感谢帮助我们优化模型')
  } catch (e) {
    ElMessage.error('反馈提交失败，请稍后重试')
  } finally {
    msg.feedbackSubmitting = false
  }
}

function openFeedbackDialog(msg) {
  feedbackDialog.value = {
    visible: true,
    message: msg,
    rating: msg.feedbackRating || 5,
    comment: '',
    submitting: false,
  }
}

async function submitFeedbackDialog() {
  const target = feedbackDialog.value.message
  if (!target?.id) return
  feedbackDialog.value.submitting = true
  target.feedbackRating = feedbackDialog.value.rating || 5
  await submitFeedback(target, feedbackDialog.value.comment)
  feedbackDialog.value.submitting = false
  feedbackDialog.value.visible = false
}
</script>

<style scoped>
/* ── Agent 状态条 ── */
.agent-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  font-size: 12px;
  color: #8a8278;
  background: #faf8f4;
  border-bottom: 1px solid #e8e2d8;
  flex-shrink: 0;
}
.agent-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  display: inline-block;
  background: #c5bdaf;
}
.agent-dot.online { background: #7eb89e; }
.agent-dot.offline { background: #c97b7b; }
.agent-sep { color: #e0d9ce; }
.mem-ring { flex-shrink: 0; }
.agent-mem { color: #b0a89e; font-size: 11px; margin-left: 2px; }

/* ── 布局 ── */
.chat-page {
  display: flex;
  gap: 16px;
  height: calc(100vh - 112px);
}

/* ── 左侧对话列表 ── */
.conv-sidebar {
  width: 240px;
  background: #fff;
  border-radius: 12px;
  padding: 14px;
  overflow-y: auto;
  flex-shrink: 0;
  border: 1px solid #e8e2d8;
  box-shadow: 0 2px 8px rgba(0,0,0,0.03);
}
.conv-actions { display: flex; gap: 8px; margin-bottom: 14px; }
.new-btn {
  flex: 1;
  --el-button-bg-color: #f5f1ec;
  --el-button-border-color: #e0d9ce;
  --el-button-text-color: #6b6054;
}
.del-btn {
  --el-button-bg-color: #fdf1f1;
  --el-button-border-color: #ecc8c8;
  --el-button-text-color: #c97b7b;
}

.conv-item {
  padding: 10px 12px;
  cursor: pointer;
  border-radius: 8px;
  margin-bottom: 4px;
  transition: all 0.2s ease;
  color: #8a8278;
  font-size: 13px;
  border-left: 3px solid transparent;
}
.conv-item:hover { background: #f5f1ec; }
.conv-item.active {
  background: #f0ebe3;
  color: #4a4238;
  border-left-color: #8b9ec9;
}
.conv-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}
.conv-time {
  font-size: 11px;
  color: #b0a89e;
  margin-top: 3px;
}

/* ── 右侧聊天区 ── */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 12px;
  padding: 18px;
  min-width: 0;
  border: 1px solid #e8e2d8;
  box-shadow: 0 2px 8px rgba(0,0,0,0.03);
}
.chat-messages { flex: 1; overflow-y: auto; margin-bottom: 14px; }
.chat-placeholder {
  text-align: center;
  color: #b0a89e;
  margin-top: 120px;
  font-size: 16px;
}

/* ── 消息气泡 ── */
.msg-row { margin-bottom: 18px; }
.msg-user-wrap { text-align: right; }
.msg-ai-wrap { text-align: left; }
.msg-img {
  width: auto;
  height: auto;
  max-width: 200px;
  max-height: 200px;
  border-radius: 10px;
  object-fit: cover;
  border: 1px solid #e8e2d8;
  flex-shrink: 0;
  margin-bottom: 4px;
}
.msg-bubble {
  display: inline-block;
  padding: 12px 18px;
  max-width: 85%;
  font-size: 14px;
  line-height: 1.7;
  text-align: left;
  border-radius: 16px;
}
.user-bubble {
  background: #f0ebe3;
  color: #4a4238;
  border-radius: 16px 16px 4px 16px;
}
.ai-bubble {
  background: #faf8f4;
  color: #4a4238;
  border-radius: 16px 16px 16px 4px;
  border: 1px solid #e8e2d8;
}
.msg-text { white-space: pre-wrap; }
.msg-cot { margin-top: 6px; max-width: 85%; }
.feedback-row {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 85%;
  margin-top: 6px;
  padding-left: 6px;
  color: #9a9085;
  font-size: 12px;
}
.feedback-label { white-space: nowrap; }
.feedback-done {
  color: #7eb89e;
  font-size: 12px;
}

/* ── 输入区 ── */
.chat-input-row { display: flex; gap: 10px; align-items: flex-end; }
.file-hidden { display: none; }
.img-btn { flex-shrink: 0; }
.msg-input { flex: 1; }
.send-btn {
  flex-shrink: 0;
  --el-button-bg-color: #6b7fa0;
  --el-button-border-color: #6b7fa0;
  --el-button-hover-bg-color: #7d90b0;
}
.img-preview {
  max-height: 100px;
  max-width: 100%;
  border-radius: 8px;
  object-fit: cover;
  border: 2px solid #e8e2d8;
}
.preview-row {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.preview-wrap {
  position: relative;
  display: inline-block;
}
.preview-badge {
  position: absolute;
  bottom: 4px;
  left: 4px;
  background: rgba(107,127,160,0.85);
  color: #fff;
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 11px;
}
.preview-remove {
  position: absolute;
  top: -8px;
  right: -8px;
  width: 22px;
  height: 22px;
  background: #c97b7b;
  color: #fff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  cursor: pointer;
  line-height: 1;
}
.msg-img-row {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.thinking-hint { color: #b8906a; font-size: 13px; padding: 8px; }

/* ── 动画 ── */
.mem-btn { --el-button-bg-color: #f0ebe3; --el-button-border-color: #e0d9ce; }
.mem-empty { color: #b0a89e; text-align: center; margin-top: 40px; }
.mem-item { padding: 10px 0; border-bottom: 1px solid #f0ebe3; }
.mem-header { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.mem-imp { color: #d4a574; font-size: 12px; }
.mem-del { color: #c5bdaf; margin-left: auto; }
.mem-content { color: #4a4238; font-size: 13px; line-height: 1.6; }

.dot-pulse::after { content: ''; animation: dots 1.5s steps(4,end) infinite; }
@keyframes dots { 0%{content:''} 25%{content:'.'} 50%{content:'..'} 75%{content:'...'} 100%{content:''} }
</style>
