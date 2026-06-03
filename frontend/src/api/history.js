import client from './index'

export const historyAPI = {
  list: (limit = 50) => client.get('/history', { params: { limit } }).then((r) => r.data),
  detail: (id) => client.get(`/history/${id}`).then((r) => r.data),
  exportExcel: (id) => client.get(`/history/${id}/export`, { responseType: 'blob' }).then((r) => {
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a')
    a.href = url; a.download = `inspection_${id}.xlsx`; a.click()
  }),
}
