import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getPipelines, createPipeline, updatePipeline, deletePipeline, getSites, getAgents, triggerRun } from '../lib/api'
import { Card, Btn, Input, Select, Toggle, PageHeader, Modal, EmptyState, Badge, Spinner } from '../components/ui'
import { Plus, Radio, Pencil, Trash2, Play, FlaskConical, GripVertical, X } from 'lucide-react'

const CRON_PRESETS = [
  { label: '7:00 AM Argentina (diario)',  value: '0 10 * * *' },
  { label: '6:00 AM Argentina (diario)',  value: '0 9 * * *'  },
  { label: '8:00 AM Argentina (diario)',  value: '0 11 * * *' },
  { label: '12:00 PM Argentina (diario)', value: '0 15 * * *' },
  { label: 'Personalizado',              value: '__custom__'  },
]

const empty = { name: '', site_id: '', cron_expr: '0 10 * * *', dry_run: false, active: true, agents: [] }

function AgentSelector({ agents, selected, onChange }) {
  const toggle = a => {
    const exists = selected.find(s => s.agent_id === a.id)
    if (exists) onChange(selected.filter(s => s.agent_id !== a.id))
    else onChange([...selected, { agent_id: a.id, run_order: selected.length, active: true }])
  }
  return (
    <div className="space-y-1.5">
      <label className="block text-xs font-medium text-slate-400 uppercase tracking-wide">Agentes asignados</label>
      <div className="space-y-1 max-h-48 overflow-y-auto scrollbar-thin">
        {agents.map((a, i) => {
          const sel = selected.find(s => s.agent_id === a.id)
          return (
            <label key={a.id} className={`flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-colors ${sel ? 'bg-blue-600/20 border border-blue-600/40' : 'bg-slate-800 border border-transparent hover:bg-slate-700'}`}>
              <input type="checkbox" className="accent-blue-500" checked={!!sel} onChange={() => toggle(a)} />
              <span className="text-sm text-slate-200">{a.name}</span>
              <Badge variant="default">{a.agent_type}</Badge>
            </label>
          )
        })}
      </div>
      {selected.length > 0 && (
        <p className="text-xs text-slate-500">{selected.length} agente(s) seleccionado(s) — corren en el orden de la lista de arriba</p>
      )}
    </div>
  )
}

export default function Pipelines() {
  const qc = useQueryClient()
  const [modal, setModal]   = useState(null)
  const [form, setForm]     = useState(empty)
  const [cronCustom, setCronCustom] = useState(false)
  const [runningId, setRunningId]   = useState(null)

  const { data: pipelines = [], isLoading } = useQuery({ queryKey: ['pipelines'], queryFn: () => getPipelines().then(r => r.data) })
  const { data: sites     = [] } = useQuery({ queryKey: ['sites'],   queryFn: () => getSites().then(r => r.data) })
  const { data: agents    = [] } = useQuery({ queryKey: ['agents'],  queryFn: () => getAgents().then(r => r.data) })

  const save = useMutation({
    mutationFn: d => modal.mode === 'edit' ? updatePipeline(modal.data.id, d) : createPipeline(d),
    onSuccess: () => { qc.invalidateQueries(['pipelines']); setModal(null) },
  })

  const remove = useMutation({
    mutationFn: id => deletePipeline(id),
    onSuccess: () => qc.invalidateQueries(['pipelines']),
  })

  const run = useMutation({
    mutationFn: ({ id, dry }) => triggerRun({ pipeline_id: id, dry_run: dry }),
    onMutate: ({ id }) => setRunningId(id),
    onSettled: () => setRunningId(null),
  })

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const openCreate = () => { setForm(empty); setCronCustom(false); setModal({ mode: 'create' }) }
  const openEdit   = p  => {
    const isCustom = !CRON_PRESETS.find(x => x.value === p.cron_expr && x.value !== '__custom__')
    setCronCustom(isCustom)
    setForm({ ...p, agents: p.agents.map(a => ({ agent_id: a.agent_id, run_order: a.run_order, active: a.active })) })
    setModal({ mode: 'edit', data: p })
  }

  const handleCronPreset = val => {
    if (val === '__custom__') { setCronCustom(true); return }
    setCronCustom(false); set('cron_expr', val)
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <PageHeader
        title="Pipelines"
        subtitle="Conectá sitios con agentes y definí el horario de publicación"
        action={<Btn onClick={openCreate}><Plus size={16} /> Nuevo pipeline</Btn>}
      />

      {isLoading ? <p className="text-slate-400 text-sm">Cargando...</p> : pipelines.length === 0 ? (
        <Card><EmptyState icon={Radio} title="Sin pipelines" description="Creá tu primer pipeline para empezar a publicar." /></Card>
      ) : (
        <div className="space-y-3">
          {pipelines.map(p => (
            <Card key={p.id}>
              <div className="px-5 py-4">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-9 h-9 rounded-lg bg-blue-600/20 flex items-center justify-center flex-shrink-0">
                    <Radio size={18} className="text-blue-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-white">{p.name}</p>
                    <p className="text-xs text-slate-500">{p.site_name} · <code className="text-slate-400">{p.cron_expr}</code></p>
                  </div>
                  <Badge variant={p.active ? 'success' : 'default'}>{p.active ? 'activo' : 'pausado'}</Badge>
                  {p.dry_run && <Badge variant="info">dry-run</Badge>}
                  <div className="flex gap-2">
                    <Btn size="sm" variant="ghost" onClick={() => openEdit(p)}><Pencil size={14} /></Btn>
                    <Btn size="sm" variant="ghost" onClick={() => { if (confirm('¿Eliminar este pipeline?')) remove.mutate(p.id) }}>
                      <Trash2 size={14} className="text-red-400" />
                    </Btn>
                  </div>
                </div>
                {/* Agentes asignados */}
                <div className="flex flex-wrap gap-1.5 ml-12 mb-3">
                  {p.agents.map(a => (
                    <span key={a.agent_id} className="text-xs bg-slate-800 text-slate-300 px-2 py-0.5 rounded border border-slate-700">
                      {a.run_order + 1}. {a.agent_name}
                    </span>
                  ))}
                </div>
                {/* Acciones */}
                <div className="flex gap-2 ml-12">
                  <Btn
                    size="sm" variant="primary"
                    disabled={!p.active || runningId === p.id}
                    onClick={() => run.mutate({ id: p.id, dry: false })}
                  >
                    {runningId === p.id ? <Spinner size={13} /> : <Play size={13} />}
                    Ejecutar ahora
                  </Btn>
                  <Btn
                    size="sm" variant="secondary"
                    disabled={runningId === p.id}
                    onClick={() => run.mutate({ id: p.id, dry: true })}
                  >
                    <FlaskConical size={13} />
                    Dry-run
                  </Btn>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.mode === 'edit' ? 'Editar pipeline' : 'Nuevo pipeline'}>
        <div className="space-y-4">
          <Input label="Nombre del pipeline" value={form.name} onChange={e => set('name', e.target.value)} placeholder="Portal Neuquén — Mañana" />

          <Select label="Sitio WordPress" value={form.site_id} onChange={e => set('site_id', parseInt(e.target.value))}>
            <option value="">Seleccioná un sitio...</option>
            {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>

          <div className="space-y-2">
            <Select label="Horario" value={cronCustom ? '__custom__' : form.cron_expr} onChange={e => handleCronPreset(e.target.value)}>
              {CRON_PRESETS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </Select>
            {cronCustom && (
              <Input placeholder="0 10 * * *  (expresión cron UTC)" value={form.cron_expr} onChange={e => set('cron_expr', e.target.value)} />
            )}
            <p className="text-xs text-slate-500">Los horarios están en UTC. Argentina = UTC−3 (en verano UTC−3).</p>
          </div>

          <AgentSelector
            agents={agents.filter(a => a.active)}
            selected={form.agents}
            onChange={v => set('agents', v)}
          />

          <div className="flex gap-4">
            <Toggle checked={form.active}  onChange={v => set('active', v)}  label="Pipeline activo" />
            <Toggle checked={form.dry_run} onChange={v => set('dry_run', v)} label="Modo dry-run" />
          </div>

          <div className="flex gap-3 pt-2">
            <Btn className="flex-1" onClick={() => save.mutate(form)} disabled={save.isPending || !form.site_id}>
              {save.isPending ? 'Guardando...' : 'Guardar pipeline'}
            </Btn>
            <Btn variant="secondary" onClick={() => setModal(null)}>Cancelar</Btn>
          </div>
          {save.isError && <p className="text-red-400 text-sm">{save.error?.response?.data?.detail || 'Error al guardar.'}</p>}
        </div>
      </Modal>
    </div>
  )
}
