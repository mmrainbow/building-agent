import client from './index'

export const adminAPI = {
  dashboard: () =>
    client.get('/admin/dashboard').then((r) => r.data),

  listFeedbacks: (params = {}) =>
    client.get('/admin/feedbacks', { params }).then((r) => r.data),

  feedbackStats: (params = {}) =>
    client.get('/admin/feedbacks/stats', { params }).then((r) => r.data),
}
