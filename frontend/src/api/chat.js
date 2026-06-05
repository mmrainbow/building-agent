import client from './index'

export const chatAPI = {
  send: (message, conversationId, imageFiles) => {
    const form = new FormData()
    if (imageFiles && imageFiles.length) {
      imageFiles.forEach(f => form.append('images', f))
    }
    const params = { message, conversation_id: conversationId || undefined }
    return client.post('/chat/send', form, { params,
      headers: imageFiles?.length ? { 'Content-Type': 'multipart/form-data' } : {},
    }).then((r) => r.data)
  },

  sendStream: (message, conversationId, imageFiles, onStep, onDone, onError) => {
    const form = new FormData()
    if (imageFiles && imageFiles.length) {
      imageFiles.forEach(f => form.append('images', f))
    }
    const token = localStorage.getItem('token')
    const params = new URLSearchParams({ message })
    if (conversationId) params.append('conversation_id', conversationId)
    fetch(`/api/chat/send/stream?${params}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: imageFiles?.length ? form : undefined,
    }).then(async (res) => {
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'step') onStep(data.data)
            else if (data.type === 'done') onDone(data)
            else if (data.type === 'error') onError(new Error(data.message))
          }
        }
      }
    }).catch(onError)
  },

  listConversations: (limit = 50) =>
    client.get('/chat/conversations', { params: { limit } }).then((r) => r.data),

  getConversation: (convId) =>
    client.get(`/chat/conversations/${convId}`).then((r) => r.data),

  deleteConversation: (convId) =>
    client.delete(`/chat/conversations/${convId}`),
}
