import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getLogs, clearLogs, getPipelines } from '../lib/api'
import { Card, CardHeader, Btn, Select, Badge, PageHeader, Spinner } from '../components/ui'
import { ScrollText, RefreshCw, Trash2, Radio } from 'lucide-react'
import clsx from 'clsx'

const STATUS_VARIANT = { published: 'success', error: 'error', skipped: 'warning', dry_run: 'info' }
const LEVEL_VARIANT  = { info: 'info', warning: 'warning', error: 'error' }

function LogRow({ log }) {
  const v = log.status ? STATUS_VARIANT[log.status] : LEVEL_VARIANT[log.level] || 'default'
  return (
    <div className="flex items-start gap-3 px-5 py-2.5 border-b border-slate-800/60 hover:bg-slate-800/30 transition-colors">
      <span className="text-xs text-slate-600 w-20 flex-shrink-0 mt-0.5 font-mono">
        {new Date(log.run_at).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
      </span>
      <Badge variant={v}>{log.status || log.level}</Badge>
      <div className="flex-1 min-w-0">
        {log.article_title
          ? <><p className="text-sm text-slate-200 truncate">{log.article_title}</p><p className="text-xs text-slate-500">{log.message}</p></>
          : <p className="text-sm text-slate-300">{log.message}</p>
        }
        {log.agent_name && <p className="text-xs text-slate-600 mt-0.5">{log.pipeline_name} · {log.agent_name}</p>}
      </div>
      {log.article_url && (
        <a href={log.article_url} target="_blank" rel="noreferrer" className="text-xs text-blue-400 hover:text-blue-300 flex-shrink-0">ver →</a>
      )}
    </div>
  )
}

export default function Logs() {
  const qc = useQueryClient()
  const [filters, setFilters] = useState({ pipeline_id: '', level: '', status: '' })
  const [streaming, setStreaming] = useState(false)
  const [streamLogs, setStreamLogs] = useState([])
  const sseRef = useRef(null)
  const bottomRef = useRef(null)

  const { data: pipelines = [] } = useQuery({ queryKey: ['pipelines'], queryFn: () => getPipelines().then(r => r.data) })

  const { data: logs = [], isLoading, refetch } = useQuery({
    queryKey: ['logs', filters],
    queryFn: () => getLogs({ ...filters, limit: 200, pipeline_id: filters.pipeline_id || undefined, level: filters.level || undefined, status: filters.status || undefined }).then(r => r.data),
    enabled: !streaming,
  })

  const remove = useMutation({
    mutationFn: () => clearLogs(filters.pipeline_id ? { pipeline_id: filters.pipeline_id } : {}),
    onSuccess: () => { qc.invalidateQueries(['logs']); setStreamLogs([]) },
  })

  const setFilter = (k, v) => setFilters(f => ({ ...f, [k]: v }))

  // SSE streaming
  const startStream = () => {
    setStreamLogs([])
    setStreaming(true)
    const token = localStorage.getItem('token')
    const url = `/api/logs/stream${filters.pipeline_id ? `?pipeline_id=${filters.pipeline_id}` : ''}`
    const es = new EventSource(url)
    es.onmessage = e => {
      try {
        const data = JSON.parse(e.data)
        setStreamLogs(prev => [data, ...prev].slice(0, 300))
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
      } catch {}
    }
    sseRef.current = es
  }

  const stopStream = () => {
    sseRef.current?.close()
    setStreaming(false)
  }

  useEffect(() => () => sseRef.current?.close(), [])

  const displayLogs = streaming ? streamLogs : logs

  return (
    <div className="p-6 max-w-5xl mx-auto flex flex-col h-full">
      <PageHeader title="Logs" subtitle="Historial de ejecuciones y errores" />

      {/* Filtros */}
      <div className="flex flex-wrap gap-3 mb-4">
        <Select value={filters.pipeline_id} onChange={e => setFilter('pipeline_id', e.target.value)} className="w-48">
          <option value="">Todos los pipelines</option>
          {pipelines.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </Select>

        <Select value={filters.level} onChange={e => setFilter('level', e.target.value)} className="w-36">
          <option value="">Todos los niveles</option>
          <option value="info">Info</option>
          <option value="warning">Warning</option>
          <option value="error">Error</option>
        </Select>

        <Select value={filters.status} onChange={e => setFilter('status', e.target.value)} className="w-40">
          <option value="">Todos los estados</option>
          <option value="published">Publicados</option>
          <option value="skipped">Skipped</option>
          <option value="error">Errores</option>
          <option value="dry_run">Dry-run</option>
        </Select>

        <div className="flex gap-2 ml-auto">
          {!streaming ? (
            <>
              <Btn size="sm" variant="secondary" onClick={() => refetch()}><RefreshCw size={14} /> Actualizar</Btn>
              <Btn size="sm" variant="success"   onClick={startStream}><Radio size={14} /> Stream en vivo</Btn>
            </>
          ) : (
            <Btn size="sm" variant="danger" onClick={stopStream}>⏹ Detener stream</Btn>
          )}
          <Btn size="sm" variant="ghost" onClick={() => { if (confirm('¿Borrar los logs filtrados?')) remove.mutate() }}>
            <Trash2 size={14} className="text-red-400" />
          </Btn>
        </div>
      </div>

      {/* Tabla de logs */}
      <Card className="flex-1 overflow-hidden flex flex-col">
        {streaming && (
          <div className="flex items-center gap-2 px-5 py-2.5 bg-emerald-900/30 border-b border-emerald-700/40 text-xs text-emerald-300">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            Streaming en vivo — {streamLogs.length} eventos recibidos
          </div>
        )}
        <div className="overflow-y-auto flex-1 scrollbar-thin">
          {isLoading && !streaming && (
            <div className="flex items-center justify-center py-16 gap-2 text-slate-400"><Spinner /> Cargando...</div>
          )}
          {!isLoading && displayLogs.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-slate-500">
              <ScrollText size={32} className="mb-3 opacity-30" />
              <p>Sin logs registrados</p>
              {streaming && <p className="text-xs mt-1">Esperando eventos del servidor...</p>}
            </div>
          )}
          {displayLogs.map(l => <LogRow key={l.id} log={l} />)}
          <div ref={bottomRef} />
        </div>
      </Card>
    </div>
  )
}
