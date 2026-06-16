import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getPipelines, getSites, getAgents, getLogs, triggerRun } from '../lib/api'
import { Card, CardHeader, CardBody, Btn, Badge, Spinner, PageHeader } from '../components/ui'
import { Play, Globe, Bot, Radio, CheckCircle, XCircle, SkipForward, FlaskConical } from 'lucide-react'
import { useState } from 'react'

const statusVariant = s => ({ published: 'success', error: 'error', skipped: 'warning', dry_run: 'info' }[s] || 'default')
const levelVariant  = l => ({ info: 'info', warning: 'warning', error: 'error' }[l] || 'default')

function StatCard({ label, value, icon: Icon, color }) {
  return (
    <Card>
      <CardBody className="flex items-center gap-4">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
          <Icon size={20} className="text-white" />
        </div>
        <div>
          <p className="text-2xl font-bold text-white">{value ?? '–'}</p>
          <p className="text-xs text-slate-400">{label}</p>
        </div>
      </CardBody>
    </Card>
  )
}

export default function Dashboard() {
  const qc = useQueryClient()
  const [runningId, setRunningId] = useState(null)

  const { data: pipelines = [] } = useQuery({ queryKey: ['pipelines'], queryFn: () => getPipelines().then(r => r.data) })
  const { data: sites     = [] } = useQuery({ queryKey: ['sites'],     queryFn: () => getSites().then(r => r.data) })
  const { data: agents    = [] } = useQuery({ queryKey: ['agents'],    queryFn: () => getAgents().then(r => r.data) })
  const { data: logs      = [] } = useQuery({
    queryKey: ['logs-recent'],
    queryFn: () => getLogs({ limit: 30 }).then(r => r.data),
    refetchInterval: 10000,
  })

  const run = useMutation({
    mutationFn: id => triggerRun({ pipeline_id: id }),
    onMutate: id => setRunningId(id),
    onSettled: () => { setRunningId(null); qc.invalidateQueries(['logs-recent']) },
  })

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <PageHeader title="Dashboard" subtitle="Resumen general del sistema" />

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label="Pipelines activos" value={pipelines.filter(p => p.active).length} icon={Radio}  color="bg-blue-600" />
        <StatCard label="Sitios WordPress"  value={sites.length}   icon={Globe} color="bg-violet-600" />
        <StatCard label="Agentes"           value={agents.length}  icon={Bot}   color="bg-emerald-600" />
        <StatCard label="Runs hoy"          value={logs.filter(l => l.status === 'published').length} icon={CheckCircle} color="bg-amber-600" />
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Pipelines */}
        <Card>
          <CardHeader>
            <h2 className="font-semibold text-white flex items-center gap-2"><Radio size={16} className="text-blue-400" /> Pipelines</h2>
          </CardHeader>
          <div className="divide-y divide-slate-800">
            {pipelines.length === 0 && (
              <p className="p-5 text-sm text-slate-500">No hay pipelines configurados.</p>
            )}
            {pipelines.map(p => (
              <div key={p.id} className="flex items-center gap-3 px-5 py-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-white truncate">{p.name}</p>
                  <p className="text-xs text-slate-500">{p.site_name} · <code className="text-slate-400">{p.cron_expr}</code></p>
                </div>
                <Badge variant={p.active ? 'success' : 'default'}>{p.active ? 'activo' : 'pausado'}</Badge>
                <Btn
                  size="sm"
                  variant="secondary"
                  disabled={!p.active || runningId === p.id}
                  onClick={() => run.mutate(p.id)}
                >
                  {runningId === p.id ? <Spinner size={14} /> : <Play size={14} />}
                  Run
                </Btn>
              </div>
            ))}
          </div>
        </Card>

        {/* Logs recientes */}
        <Card>
          <CardHeader className="flex items-center justify-between">
            <h2 className="font-semibold text-white">Actividad reciente</h2>
            <span className="text-xs text-slate-500">actualiza cada 10s</span>
          </CardHeader>
          <div className="divide-y divide-slate-800 max-h-80 overflow-y-auto scrollbar-thin">
            {logs.length === 0 && (
              <p className="p-5 text-sm text-slate-500">Sin actividad registrada.</p>
            )}
            {logs.map(l => (
              <div key={l.id} className="px-5 py-2.5 flex items-start gap-3">
                <Badge variant={l.status ? statusVariant(l.status) : levelVariant(l.level)} >
                  {l.status || l.level}
                </Badge>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-slate-300 truncate">{l.article_title || l.message}</p>
                  <p className="text-xs text-slate-600 mt-0.5">{l.agent_name} · {new Date(l.run_at).toLocaleTimeString('es-AR')}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}
