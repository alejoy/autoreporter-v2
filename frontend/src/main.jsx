import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'

import { isLoggedIn } from './lib/auth'
import Layout    from './components/Layout'
import Login     from './pages/Login'
import Dashboard from './pages/Dashboard'
import Sites     from './pages/Sites'
import LLMConfigs from './pages/LLMConfigs'
import Agents    from './pages/Agents'
import Pipelines from './pages/Pipelines'
import Logs      from './pages/Logs'

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000 } } })

function Protected({ children }) {
  return isLoggedIn() ? children : <Navigate to="/login" replace />
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/*" element={
            <Protected>
              <Layout>
                <Routes>
                  <Route path="/"          element={<Dashboard />} />
                  <Route path="/pipelines" element={<Pipelines />} />
                  <Route path="/agents"    element={<Agents />} />
                  <Route path="/sites"     element={<Sites />} />
                  <Route path="/llm"       element={<LLMConfigs />} />
                  <Route path="/logs"      element={<Logs />} />
                  <Route path="*"          element={<Navigate to="/" replace />} />
                </Routes>
              </Layout>
            </Protected>
          } />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>
)
