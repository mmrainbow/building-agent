import client from './index'

export const historyAPI = {
  list: (limit = 50) => client.get('/history', { params: { limit } }).then((r) => r.data),
  detail: (id) => client.get(`/history/${id}`).then((r) => r.data),
  exportFile: (id, format = 'xlsx') => client.get(`/history/${id}/export`, {
    params: { format },
    responseType: 'blob',
  }).then((r) => {
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a')
    a.href = url; a.download = `inspection_${id}.${format}`; a.click()
    URL.revokeObjectURL(url)
  }),
  exportExcel: (id) => historyAPI.exportFile(id, 'xlsx'),
}
