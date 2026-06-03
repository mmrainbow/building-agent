import client from './index'

export const inspectionAPI = {
  multi: (images, message = '') => {
    const form = new FormData()
    images.forEach((img) => form.append('images', img))
    return client.post('/inspection/multi', form, {
      params: { message },
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },
}
