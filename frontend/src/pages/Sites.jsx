import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSites, createSite, updateSite, deleteSite } from '../lib/api'
import { Card, Btn, Input, Toggle, PageHeader, Modal, EmptyState, Badge } from '../components/ui'
import { Plus, Globe, Pencil, Trash2 } from 'lucide-react'

const empty = { name: '', wp_url: '', wp_user: '', wp_password: '', active: true }

export default function Sites() {
  const qc = useQueryClient()
  const [modal, setModal] = useState(null)   // null | { mode: 'create'|'edit', data }
  const [form, setForm] = useState(empty)

  const { data: sites = [], isLoading } = useQuery({
    queryKey: ['sites'],
    queryFn: () => getSites().then(r => r.data),
  })

  const save = useMutation({
    mutationFn: d => modal.mode === 'edit' ? updateSite(modal.data.id, d) : createSite(d),
    onSuccess: () => { qc.invalidateQueries(['sites']); setModal(null) },
  })

  const remove = useMutation({
    mutationFn: id => deleteSite(id),
    onSuccess: () => qc.invalidateQueries(['sites']),
  })

  const openCreate = () => { setForm(empty); setModal({ mode: 'create' }) }
  const openEdit   = s  => { setForm({ ...s, wp_password: '' }); setModal({ mode: 'edit', data: s }) }

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <PageHeader
        title="Sitios WordPress"
        subtitle="Gestioná los portales donde se publican las noticias"
        action={<Btn onClick={openCreate}><Plus size={16} /> Nuevo sitio</Btn>}
      />

      {isLoading ? (
        <p className="text-slate-400 text-sm">Cargando...</p>
      ) : sites.length === 0 ? (
        <Card><EmptyState icon={Globe} title="Sin sitios" description="Agregá tu primer portal WordPress." /></Card>
      ) : (
        <div className="space-y-3">
          {sites.map(s => (
            <Card key={s.id}>
              <div className="flex items-center gap-4 px-5 py-4">
                <div className="w-9 h-9 rounded-lg bg-violet-600/20 flex items-center justify-center flex-shrink-0">
                  <Globe size={18} className="text-violet-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-white">{s.name}</p>
                  <p className="text-xs text-slate-500 truncate">{s.wp_url} · usuario: {s.wp_user}</p>
                </div>
                <Badge variant={s.active ? 'success' : 'default'}>{s.active ? 'activo' : 'inactivo'}</Badge>
                <div className="flex gap-2">
                  <Btn size="sm" variant="ghost" onClick={() => openEdit(s)}><Pencil size={14} /></Btn>
                  <Btn size="sm" variant="ghost" onClick={() => { if (confirm('¿Eliminar este sitio?')) remove.mutate(s.id) }}>
                    <Trash2 size={14} className="text-red-400" />
                  </Btn>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.mode === 'edit' ? 'Editar sitio' : 'Nuevo sitio WordPress'}>
        <div className="space-y-4">
          <Input label="Nombre del portal" value={form.name} onChange={e => set('name', e.target.value)} placeholder="Portal Neuquén" />
          <Input label="URL de WordPress" value={form.wp_url} onChange={e => set('wp_url', e.target.value)} placeholder="https://miportal.com" />
          <Input label="Usuario WordPress" value={form.wp_user} onChange={e => set('wp_user', e.target.value)} placeholder="admin" />
          <Input label="Application Password" type="password" value={form.wp_password} onChange={e => set('wp_password', e.target.value)} placeholder={modal?.mode === 'edit' ? 'Dejar vacío para no cambiar' : 'xxxx xxxx xxxx xxxx'} />
          <Toggle checked={form.active} onChange={v => set('active', v)} label="Sitio activo" />
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
