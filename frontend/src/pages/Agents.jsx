import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getAgents, createAgent, updateAgent, deleteAgent, getLLMConfigs } from '../lib/api'
import { Card, Btn, Input, Textarea, Select, Toggle, PageHeader, Modal, EmptyState, Badge } from '../components/ui'
import { Plus, Bot, Pencil, Trash2, Link, X } from 'lucide-react'

const AGENT_TYPES = ['municipal','provincial','nacional','internacional','sociedad','clima','horoscopo']

const empty = {
  name: '', agent_type: 'nacional',
  prompt_selection: '', prompt_writing: '',
  keywords_required: [], keywords_skip: [],
  max_topics: 3, wp_category: '', llm_config_id: null,
  fallback_llm_config_id: null, wp_author_id: null, post_status: 'publish',
  extra_config: {},
  active: true,
  feeds: [],
}

const EXTRA_CONFIG_HINTS = {
  horoscopo: '{\n  "imagen_url": "https://tusitio.com/wp-content/uploads/horoscopo.jpg",\n  "tono": "místico, inspirador y útil"\n}',
  clima: '{\n  "ciudad": "Bariloche",\n  "lat": -41.1335,\n  "lon": -71.3103,\n  "smn_keywords": ["bariloche", "rio negro", "andina"]\n}',
}

const CLIMA_ESTILOS = [
  { value: 'clasico',     label: 'Clásico — degradé full-bleed, temperatura gigante' },
  { value: 'moderno',     label: 'Moderno — tarjeta clara redondeada' },
  { value: 'profesional', label: 'Profesional — íconos vectoriales + glass bar (recomendado)' },
]

function safeParseJSON(text) {
  try {
    return text.trim() ? JSON.parse(text) : {}
  } catch {
    return null
  }
}

function ExtraConfigEditor({ agentType, value, onChange }) {
  const [text, setText] = useState(JSON.stringify(value || {}, null, 2))
  const [error, setError] = useState(null)

  const handleChange = raw => {
    setText(raw)
    const parsed = safeParseJSON(raw)
    if (parsed) {
      onChange(parsed)
      setError(null)
    } else {
      setError('JSON inválido — se ignora hasta que lo corrijas')
    }
  }

  const handleEstiloSelect = estilo => {
    const current = safeParseJSON(text) || {}
    const next = { ...current, estilo }
    const nextText = JSON.stringify(next, null, 2)
    setText(nextText)
    onChange(next)
    setError(null)
  }

  if (!['horoscopo', 'clima'].includes(agentType)) return null

  const estiloActual = (safeParseJSON(text) || {}).estilo || 'clasico'

  return (
    <div className="space-y-3">
      {agentType === 'clima' && (
        <Select
          label="Estilo de la placa de imagen"
          value={estiloActual}
          onChange={e => handleEstiloSelect(e.target.value)}
        >
          {CLIMA_ESTILOS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </Select>
      )}
      <div className="space-y-1.5">
        <label className="block text-xs font-medium text-slate-400 uppercase tracking-wide">
          Configuración extra (JSON) — específica de "{agentType}"
        </label>
        <textarea
          rows={5}
          value={text}
          onChange={e => handleChange(e.target.value)}
          placeholder={EXTRA_CONFIG_HINTS[agentType]}
          className="w-full font-mono bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-100 placeholder-slate-500 outline-none focus:border-blue-500"
        />
        <p className="text-xs text-slate-500">
          Ej: {EXTRA_CONFIG_HINTS[agentType].replace(/\n\s*/g, ' ')}
        </p>
        {error && <p className="text-xs text-red-400">{error}</p>}
      </div>
    </div>
  )
}

function FeedsEditor({ feeds, onChange }) {
  const add    = () => onChange([...feeds, { url: '', label: '', active: true }])
  const remove = i  => onChange(feeds.filter((_, j) => j !== i))
  const set    = (i, k, v) => onChange(feeds.map((f, j) => j === i ? { ...f, [k]: v } : f))

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">RSS Feeds</label>
        <Btn size="sm" variant="ghost" onClick={add}><Plus size={13} /> Agregar</Btn>
      </div>
      {feeds.length === 0 && (
        <p className="text-xs text-slate-500 py-2">Sin feeds. Hacé clic en "Agregar" para añadir URLs RSS.</p>
      )}
      {feeds.map((f, i) => (
        <div key={i} className="flex gap-2 items-start">
          <div className="flex-1 space-y-1">
            <input
              placeholder="https://ejemplo.com/rss.xml"
              value={f.url}
              onChange={e => set(i, 'url', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-100 placeholder-slate-500 outline-none focus:border-blue-500"
            />
            <input
              placeholder="Etiqueta (opcional)"
              value={f.label || ''}
              onChange={e => set(i, 'label', e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-100 placeholder-slate-500 outline-none focus:border-blue-500"
            />
          </div>
          <button onClick={() => remove(i)} className="mt-1 text-slate-500 hover:text-red-400 transition-colors"><X size={15} /></button>
        </div>
      ))}
    </div>
  )
}

function KeywordsInput({ label, value = [], onChange }) {
  const [input, setInput] = useState('')
  const add = () => {
    const kw = input.trim().toLowerCase()
    if (kw && !value.includes(kw)) onChange([...value, kw])
    setInput('')
  }
  return (
    <div className="space-y-1.5">
      <label className="block text-xs font-medium text-slate-400 uppercase tracking-wide">{label}</label>
      <div className="flex gap-2">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), add())}
          placeholder="Escribí y presioná Enter"
          className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-100 placeholder-slate-500 outline-none focus:border-blue-500"
        />
        <Btn size="sm" variant="secondary" onClick={add}>+</Btn>
      </div>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {value.map(kw => (
            <span key={kw} className="inline-flex items-center gap-1 bg-slate-700 text-slate-300 text-xs px-2 py-0.5 rounded">
              {kw}
              <button onClick={() => onChange(value.filter(k => k !== kw))} className="text-slate-400 hover:text-red-400"><X size={10} /></button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Agents() {
  const qc = useQueryClient()
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState(empty)

  const { data: agents  = [], isLoading } = useQuery({ queryKey: ['agents'],     queryFn: () => getAgents().then(r => r.data) })
  const { data: llms    = [] }            = useQuery({ queryKey: ['llm-configs'], queryFn: () => getLLMConfigs().then(r => r.data) })

  const save = useMutation({
    mutationFn: d => modal.mode === 'edit' ? updateAgent(modal.data.id, d) : createAgent(d),
    onSuccess: () => { qc.invalidateQueries(['agents']); setModal(null) },
  })

  const remove = useMutation({
    mutationFn: id => deleteAgent(id),
    onSuccess: () => qc.invalidateQueries(['agents']),
  })

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const openCreate = () => { setForm(empty); setModal({ mode: 'create' }) }
  const openEdit   = a  => { setForm({
    ...a,
    llm_config_id: a.llm_config_id ?? null,
    fallback_llm_config_id: a.fallback_llm_config_id ?? null,
    wp_author_id: a.wp_author_id ?? null,
    post_status: a.post_status || 'publish',
    extra_config: a.extra_config || {},
  }); setModal({ mode: 'edit', data: a }) }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <PageHeader
        title="Agentes"
        subtitle="Configurá los agentes de noticias, sus prompts y feeds RSS"
        action={<Btn onClick={openCreate}><Plus size={16} /> Nuevo agente</Btn>}
      />

      {isLoading ? <p className="text-slate-400 text-sm">Cargando...</p> : agents.length === 0 ? (
        <Card><EmptyState icon={Bot} title="Sin agentes" description="Creá tu primer agente de noticias." /></Card>
      ) : (
        <div className="space-y-3">
          {agents.map(a => (
            <Card key={a.id}>
              <div className="flex items-center gap-4 px-5 py-4">
                <div className="w-9 h-9 rounded-lg bg-emerald-600/20 flex items-center justify-center flex-shrink-0">
                  <Bot size={18} className="text-emerald-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-white">{a.name}</p>
                  <p className="text-xs text-slate-500">
                    tipo: <span className="text-slate-400">{a.agent_type}</span>
                    {' · '}{a.feeds?.length || 0} feeds
                    {' · '}{a.max_topics} temas máx
                    {a.wp_category && ` · cat: ${a.wp_category}`}
                    {a.wp_author_id && ` · autor WP: ${a.wp_author_id}`}
                  </p>
                </div>
                {a.post_status === 'draft' && <Badge variant="info">borrador</Badge>}
                <Badge variant={a.active ? 'success' : 'default'}>{a.active ? 'activo' : 'inactivo'}</Badge>
                <div className="flex gap-2">
                  <Btn size="sm" variant="ghost" onClick={() => openEdit(a)}><Pencil size={14} /></Btn>
                  <Btn size="sm" variant="ghost" onClick={() => { if (confirm('¿Eliminar este agente?')) remove.mutate(a.id) }}>
                    <Trash2 size={14} className="text-red-400" />
                  </Btn>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.mode === 'edit' ? 'Editar agente' : 'Nuevo agente'}>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Input label="Nombre" value={form.name} onChange={e => set('name', e.target.value)} placeholder="Municipal Neuquén" />
            <Select label="Tipo" value={form.agent_type} onChange={e => set('agent_type', e.target.value)}>
              {AGENT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </Select>
          </div>

          <Textarea
            label="Prompt — Selección de noticias"
            value={form.prompt_selection}
            onChange={e => set('prompt_selection', e.target.value)}
            rows={4}
            placeholder="Elegí los 3 más relevantes sobre..."
          />
          <Textarea
            label="Prompt — Redacción del artículo"
            value={form.prompt_writing}
            onChange={e => set('prompt_writing', e.target.value)}
            rows={2}
            placeholder="Sos un redactor periodístico para..."
          />

          <div className="grid grid-cols-2 gap-3">
            <Input label="Categoría WordPress" value={form.wp_category || ''} onChange={e => set('wp_category', e.target.value)} placeholder="MUNICIPALES" />
            <Input label="Máx temas por run" type="number" min="1" max="10" value={form.max_topics} onChange={e => set('max_topics', parseInt(e.target.value))} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Select label="Modelo LLM" value={form.llm_config_id ?? ''} onChange={e => set('llm_config_id', e.target.value ? parseInt(e.target.value) : null)}>
              <option value="">Sin asignar</option>
              {llms.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
            </Select>
            <Select label="LLM de respaldo (si el primario falla)" value={form.fallback_llm_config_id ?? ''} onChange={e => set('fallback_llm_config_id', e.target.value ? parseInt(e.target.value) : null)}>
              <option value="">Sin respaldo</option>
              {llms.filter(l => l.id !== form.llm_config_id).map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Input
              label="ID de usuario WordPress (autor)"
              type="number"
              value={form.wp_author_id ?? ''}
              onChange={e => set('wp_author_id', e.target.value ? parseInt(e.target.value) : null)}
              placeholder="Dejar vacío = autor por defecto"
            />
            <Select label="Estado de publicación" value={form.post_status} onChange={e => set('post_status', e.target.value)}>
              <option value="publish">Publicar directo</option>
              <option value="draft">Guardar como borrador</option>
            </Select>
          </div>

          <ExtraConfigEditor
            key={modal?.data?.id || 'new'}
            agentType={form.agent_type}
            value={form.extra_config}
            onChange={v => set('extra_config', v)}
          />

          <KeywordsInput
            label="Keywords requeridas (al menos una en el titular)"
            value={form.keywords_required || []}
            onChange={v => set('keywords_required', v)}
          />
          <KeywordsInput
            label="Keywords a ignorar (skip si aparece en titular)"
            value={form.keywords_skip || []}
            onChange={v => set('keywords_skip', v)}
          />

          <FeedsEditor feeds={form.feeds || []} onChange={v => set('feeds', v)} />

          <Toggle checked={form.active} onChange={v => set('active', v)} label="Agente activo" />

          <div className="flex gap-3 pt-2">
            <Btn className="flex-1" onClick={() => save.mutate(form)} disabled={save.isPending}>
              {save.isPending ? 'Guardando...' : 'Guardar agente'}
            </Btn>
            <Btn variant="secondary" onClick={() => setModal(null)}>Cancelar</Btn>
          </div>
          {save.isError && <p className="text-red-400 text-sm">{save.error?.response?.data?.detail || 'Error al guardar.'}</p>}
        </div>
      </Modal>
    </div>
  )
}
