import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getLLMConfigs, createLLMConfig, updateLLMConfig, deleteLLMConfig } from '../lib/api'
import { Card, Btn, Input, Select, Toggle, PageHeader, Modal, EmptyState, Badge } from '../components/ui'
import { Plus, Settings, Pencil, Trash2 } from 'lucide-react'

const PROVIDERS = [
  { value: 'gemini',     label: 'Google Gemini' },
  { value: 'openai',     label: 'OpenAI' },
  { value: 'anthropic',  label: 'Anthropic (Claude)' },
  { value: 'openrouter', label: 'OpenRouter (multi-proveedor, tiene modelos gratis)' },
]

const MODELS = {
  gemini:     ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-1.5-flash'],
  openai:     ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'],
  anthropic:  ['claude-sonnet-4-6', 'claude-haiku-4-5', 'claude-opus-4-8'],
  openrouter: ['google/gemini-2.0-flash-exp:free', 'meta-llama/llama-3.1-8b-instruct:free', 'anthropic/claude-3.5-haiku'],
}

const empty = { name: '', provider: 'gemini', model_name: 'gemini-2.5-flash', api_key: '', temperature: 0.5, max_tokens: 1500, active: true }

export default function LLMConfigs() {
  const qc = useQueryClient()
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState(empty)

  const { data: configs = [], isLoading } = useQuery({
    queryKey: ['llm-configs'],
    queryFn: () => getLLMConfigs().then(r => r.data),
  })

  const save = useMutation({
    mutationFn: d => modal.mode === 'edit' ? updateLLMConfig(modal.data.id, d) : createLLMConfig(d),
    onSuccess: () => { qc.invalidateQueries(['llm-configs']); setModal(null) },
  })

  const remove = useMutation({
    mutationFn: id => deleteLLMConfig(id),
    onSuccess: () => qc.invalidateQueries(['llm-configs']),
  })

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const openCreate = () => { setForm(empty); setModal({ mode: 'create' }) }
  const openEdit   = c  => { setForm({ ...c, api_key: '' }); setModal({ mode: 'edit', data: c }) }

  const providerLabel = p => PROVIDERS.find(x => x.value === p)?.label || p

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <PageHeader
        title="Modelos LLM"
        subtitle="Configurá los proveedores de IA para tus agentes"
        action={<Btn onClick={openCreate}><Plus size={16} /> Nuevo modelo</Btn>}
      />

      {isLoading ? <p className="text-slate-400 text-sm">Cargando...</p> : configs.length === 0 ? (
        <Card><EmptyState icon={Settings} title="Sin modelos" description="Agregá tu primer proveedor de IA." /></Card>
      ) : (
        <div className="space-y-3">
          {configs.map(c => (
            <Card key={c.id}>
              <div className="flex items-center gap-4 px-5 py-4">
                <div className="w-9 h-9 rounded-lg bg-purple-600/20 flex items-center justify-center flex-shrink-0">
                  <Settings size={18} className="text-purple-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-white">{c.name}</p>
                  <p className="text-xs text-slate-500">{providerLabel(c.provider)} · <code className="text-slate-400">{c.model_name}</code> · temp {c.temperature}</p>
                </div>
                <Badge variant={c.active ? 'success' : 'default'}>{c.active ? 'activo' : 'inactivo'}</Badge>
                <div className="flex gap-2">
                  <Btn size="sm" variant="ghost" onClick={() => openEdit(c)}><Pencil size={14} /></Btn>
                  <Btn size="sm" variant="ghost" onClick={() => { if (confirm('¿Eliminar?')) remove.mutate(c.id) }}>
                    <Trash2 size={14} className="text-red-400" />
                  </Btn>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.mode === 'edit' ? 'Editar modelo LLM' : 'Nuevo modelo LLM'}>
        <div className="space-y-4">
          <Input label="Nombre" value={form.name} onChange={e => set('name', e.target.value)} placeholder="Gemini Flash" />
          <Select label="Proveedor" value={form.provider} onChange={e => { set('provider', e.target.value); set('model_name', MODELS[e.target.value]?.[0] || '') }}>
            {PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
          </Select>
          <Select label="Modelo" value={form.model_name} onChange={e => set('model_name', e.target.value)}>
            {(MODELS[form.provider] || []).map(m => <option key={m} value={m}>{m}</option>)}
            <option value="__custom__">Personalizado...</option>
          </Select>
          {form.model_name === '__custom__' && (
            <Input label="Nombre del modelo (custom)" value={form._custom || ''} onChange={e => { set('_custom', e.target.value); set('model_name', e.target.value) }} placeholder="mi-modelo-fine-tuned" />
          )}
          <Input label="API Key" type="password" value={form.api_key} onChange={e => set('api_key', e.target.value)} placeholder={modal?.mode === 'edit' ? 'Dejar vacío para no cambiar' : 'sk-...'} />
          <div className="grid grid-cols-2 gap-3">
            <Input label="Temperatura (0–1)" type="number" min="0" max="1" step="0.1" value={form.temperature} onChange={e => set('temperature', parseFloat(e.target.value))} />
            <Input label="Max tokens" type="number" value={form.max_tokens} onChange={e => set('max_tokens', parseInt(e.target.value))} />
          </div>
          <Toggle checked={form.active} onChange={v => set('active', v)} label="Modelo activo" />
          <div className="flex gap-3 pt-2">
            <Btn className="flex-1" onClick={() => save.mutate(form)} disabled={save.isPending}>
              {save.isPending ? 'Guardando...' : 'Guardar'}
            </Btn>
            <Btn variant="secondary" onClick={() => setModal(null)}>Cancelar</Btn>
          </div>
          {save.isError && <p className="text-red-400 text-sm">{save.error?.response?.data?.detail || 'Error al guardar.'}</p>}
        </div>
      </Modal>
    </div>
  )
}
