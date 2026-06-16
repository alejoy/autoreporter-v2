import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api

// ── Auth ──────────────────────────────────────────────────────
export const login = (username, password) => {
  const form = new URLSearchParams({ username, password })
  return api.post('/auth/login', form, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
}

// ── Sites ─────────────────────────────────────────────────────
export const getSites    = ()         => api.get('/sites/')
export const createSite  = data       => api.post('/sites/', data)
export const updateSite  = (id, data) => api.put(`/sites/${id}`, data)
export const deleteSite  = id         => api.delete(`/sites/${id}`)

// ── LLM Configs ───────────────────────────────────────────────
export const getLLMConfigs   = ()         => api.get('/llm-configs/')
export const createLLMConfig = data       => api.post('/llm-configs/', data)
export const updateLLMConfig = (id, data) => api.put(`/llm-configs/${id}`, data)
export const deleteLLMConfig = id         => api.delete(`/llm-configs/${id}`)

// ── Agents ────────────────────────────────────────────────────
export const getAgents   = ()         => api.get('/agents/')
export const createAgent = data       => api.post('/agents/', data)
export const updateAgent = (id, data) => api.put(`/agents/${id}`, data)
export const deleteAgent = id         => api.delete(`/agents/${id}`)

// ── Pipelines ─────────────────────────────────────────────────
export const getPipelines   = ()         => api.get('/pipelines/')
export const createPipeline = data       => api.post('/pipelines/', data)
export const updatePipeline = (id, data) => api.put(`/pipelines/${id}`, data)
export const deletePipeline = id         => api.delete(`/pipelines/${id}`)

// ── Runs ──────────────────────────────────────────────────────
export const triggerRun = data => api.post('/runs/', data)

// ── Logs ──────────────────────────────────────────────────────
export const getLogs   = params => api.get('/logs/', { params })
export const clearLogs = params => api.delete('/logs/', { params })
