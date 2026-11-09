import axios from 'axios'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api',
  timeout: 12000,
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail
    if (Array.isArray(detail)) {
      error.response.data.detail = detail
        .map((item) => item.msg || 'Invalid value')
        .join('. ')
    } else if (detail && typeof detail === 'object') {
      error.response.data.detail = detail.message || 'The request could not be completed.'
    }
    return Promise.reject(error)
  },
)

export function setToken(token) {
  if (token) api.defaults.headers.common.Authorization = `Bearer ${token}`
  else delete api.defaults.headers.common.Authorization
}
