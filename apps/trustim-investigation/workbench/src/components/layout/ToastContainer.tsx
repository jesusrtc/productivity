import { useToastStore, type Toast } from '../../store/toast'

const TYPE_STYLES: Record<Toast['type'], string> = {
  info: 'border-accent-blue/30 text-gray-200',
  success: 'border-green-500/30 text-green-200',
  warning: 'border-yellow-500/30 text-yellow-200',
  error: 'border-red-500/30 text-red-200',
}

const TYPE_ICONS: Record<Toast['type'], string> = {
  info: '\u2139\uFE0F',
  success: '\u2705',
  warning: '\u26A0\uFE0F',
  error: '\u274C',
}

export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts)
  const removeToast = useToastStore((s) => s.removeToast)

  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-5 right-5 z-[200] flex flex-col gap-2.5 pointer-events-none">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`pointer-events-auto glass-panel border rounded-2xl px-4 py-3 shadow-2xl text-[13px] flex items-center gap-3 animate-[slideIn_0.25s_cubic-bezier(0.16,1,0.3,1)] max-w-[380px] ${TYPE_STYLES[toast.type]}`}
          role="alert"
        >
          <span className="text-base flex-shrink-0">{TYPE_ICONS[toast.type]}</span>
          <span className="flex-1 leading-snug">{toast.message}</span>
          <button
            onClick={() => removeToast(toast.id)}
            className="text-gray-500 hover:text-gray-300 flex-shrink-0 ml-1"
            aria-label="Dismiss notification"
          >
            {'\u2715'}
          </button>
        </div>
      ))}
    </div>
  )
}
