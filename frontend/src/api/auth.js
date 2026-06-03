import client from './index'

export const authAPI = {
  login: (username, password) =>
    client.post('/login', { username, password }).then((r) => r.data),
  register: (username, password) =>
    client.post('/register', { username, password }).then((r) => r.data),
}
