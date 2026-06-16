import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Newspaper } from 'lucide-react'
import { login } from '../lib/api'
import { setToken } from '../lib/auth'

export default function Login() {
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async e => {
    e.preventDefault()
    setError('')
    setLoading(true)
    const { username, password } = e.target.elements
    try {
      const res = await login(username.value, password.value)
      setToken(res.data.access_token)
      navigate('/')
    } catch {
      setError('Usuario o contraseña incorrectos.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-blue-600 mb-4 shadow-lg shadow-blue-600/30">
            <Newspaper size={28} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">AutoReporter</h1>
          <p className="text-slate-400 text-sm mt-1">Panel de administración v2</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4 shadow-xl">
          <div>
            <label className="block text-xs font-medium text-slate-400 uppercase tracking-wide mb-1">Usuario</label>
            <input
              name="username"
              defaultValue="admin"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-blue-500 transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 uppercase tracking-wide mb-1">Contraseña</label>
            <input
              name="password"
              type="password"
              autoFocus
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-blue-500 transition-colors"
            />
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold py-2.5 rounded-lg transition-colors"
          >
            {loading ? 'Ingresando...' : 'Ingresar'}
          </button>
        </form>
      </div>
    </div>
  )
}
