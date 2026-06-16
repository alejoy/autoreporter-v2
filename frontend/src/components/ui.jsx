import clsx from 'clsx'

export function Card({ children, className }) {
  return <div className={clsx('bg-slate-900 border border-slate-800 rounded-xl', className)}>{children}</div>
}

export function CardHeader({ children, className }) {
  return <div className={clsx('px-5 py-4 border-b border-slate-800', className)}>{children}</div>
}

export function CardBody({ children, className }) {
  return <div className={clsx('p-5', className)}>{children}</div>
}

export function Btn({ children, variant = 'primary', size = 'md', className, ...props }) {
  return (
    <button
      className={clsx(
        'inline-flex items-center gap-2 font-medium rounded-lg transition-colors disabled:opacity-50',
        size === 'sm' && 'px-3 py-1.5 text-sm',
        size === 'md' && 'px-4 py-2 text-sm',
        size === 'lg' && 'px-5 py-2.5 text-base',
        variant === 'primary'   && 'bg-blue-600 hover:bg-blue-500 text-white',
        variant === 'secondary' && 'bg-slate-700 hover:bg-slate-600 text-slate-100',
        variant === 'danger'    && 'bg-red-600 hover:bg-red-500 text-white',
        variant === 'ghost'     && 'text-slate-400 hover:text-white hover:bg-slate-800',
        variant === 'success'   && 'bg-emerald-600 hover:bg-emerald-500 text-white',
        className
      )}
      {...props}
    >
      {children}
    </button>
  )
}

export function Input({ label, error, className, ...props }) {
  return (
    <div className={clsx('space-y-1', className)}>
      {label && <label className="block text-xs font-medium text-slate-400 uppercase tracking-wide">{label}</label>}
      <input
        className={clsx(
          'w-full bg-slate-800 border rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none transition-colors',
          error ? 'border-red-500 focus:border-red-400' : 'border-slate-700 focus:border-blue-500'
        )}
        {...props}
      />
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}

export function Textarea({ label, error, className, ...props }) {
  return (
    <div className={clsx('space-y-1', className)}>
      {label && <label className="block text-xs font-medium text-slate-400 uppercase tracking-wide">{label}</label>}
      <textarea
        className={clsx(
          'w-full bg-slate-800 border rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none transition-colors resize-none',
          error ? 'border-red-500' : 'border-slate-700 focus:border-blue-500'
        )}
        {...props}
      />
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}

export function Select({ label, error, children, className, ...props }) {
  return (
    <div className={clsx('space-y-1', className)}>
      {label && <label className="block text-xs font-medium text-slate-400 uppercase tracking-wide">{label}</label>}
      <select
        className={clsx(
          'w-full bg-slate-800 border rounded-lg px-3 py-2 text-sm text-slate-100 outline-none transition-colors',
          error ? 'border-red-500' : 'border-slate-700 focus:border-blue-500'
        )}
        {...props}
      >
        {children}
      </select>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}

export function Toggle({ checked, onChange, label }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer">
      <div className="relative">
        <input type="checkbox" className="sr-only" checked={checked} onChange={e => onChange(e.target.checked)} />
        <div className={clsx('w-10 h-5 rounded-full transition-colors', checked ? 'bg-blue-600' : 'bg-slate-700')} />
        <div className={clsx('absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform', checked && 'translate-x-5')} />
      </div>
      {label && <span className="text-sm text-slate-300">{label}</span>}
    </label>
  )
}

export function Badge({ children, variant = 'default' }) {
  return (
    <span className={clsx(
      'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium',
      variant === 'default'   && 'bg-slate-700 text-slate-300',
      variant === 'success'   && 'bg-emerald-900 text-emerald-300',
      variant === 'error'     && 'bg-red-900 text-red-300',
      variant === 'warning'   && 'bg-amber-900 text-amber-300',
      variant === 'info'      && 'bg-blue-900 text-blue-300',
      variant === 'purple'    && 'bg-purple-900 text-purple-300',
    )}>
      {children}
    </span>
  )
}

export function Spinner({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className="animate-spin text-blue-400">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="31.416" strokeDashoffset="10" strokeLinecap="round" />
    </svg>
  )
}

export function PageHeader({ title, subtitle, action }) {
  return (
    <div className="flex items-start justify-between mb-6">
      <div>
        <h1 className="text-xl font-bold text-white">{title}</h1>
        {subtitle && <p className="text-sm text-slate-400 mt-0.5">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

export function EmptyState({ icon: Icon, title, description }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-12 h-12 rounded-xl bg-slate-800 flex items-center justify-center mb-4">
        <Icon size={24} className="text-slate-500" />
      </div>
      <p className="text-slate-300 font-medium">{title}</p>
      {description && <p className="text-slate-500 text-sm mt-1">{description}</p>}
    </div>
  )
}

export function Modal({ open, onClose, title, children }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-lg max-h-[90vh] flex flex-col shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h2 className="font-semibold text-white">{title}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white text-lg leading-none">✕</button>
        </div>
        <div className="overflow-y-auto flex-1 p-5 scrollbar-thin">
          {children}
        </div>
      </div>
    </div>
  )
}
