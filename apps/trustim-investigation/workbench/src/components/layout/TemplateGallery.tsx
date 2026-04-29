import { useState, useEffect } from 'react'
import { miscApi } from '../../api'

interface Template {
  id: string
  name: string
  description: string
  skills: string[]
  steps?: { label: string; query_template: string }[]
  created_at: string
}

interface Props {
  onClose: () => void
  onUseTemplate: (prompt: string) => void
}

/** Gallery of saved investigation templates */
export function TemplateGallery({ onClose, onUseTemplate }: Props) {
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  useEffect(() => {
    miscApi.listTemplates()
      .then(setTemplates)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleDelete = (id: string) => {
    if (confirm('Delete this template?')) {
      miscApi.deleteTemplate(id)
        .then(() => setTemplates(prev => prev.filter(t => t.id !== id)))
    }
  }

  const handleUse = (template: Template) => {
    const stepList = template.steps?.map(s => s.label).join(', ') || template.skills.join(', ')
    const prompt = `Run investigation using template "${template.name}". Steps: ${stepList}. Use the skills: ${template.skills.join(', ')}. Execute each step sequentially with execute_trino_query.`
    onUseTemplate(prompt)
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[100]" onClick={onClose}>
      <div className="glass-panel rounded-2xl p-6 w-[560px] max-h-[80vh] flex flex-col animate-[fadeIn_0.2s_ease-out]" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-medium text-gray-200">Investigation Templates</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-200">{'\u2715'}</button>
        </div>

        <div className="flex-1 overflow-y-auto space-y-2">
          {loading ? (
            <div className="space-y-2">
              {[1,2,3].map(i => (
                <div key={i} className="bg-white/[0.02] rounded-lg px-3 py-3 animate-pulse">
                  <div className="h-3 bg-surface-3 rounded w-3/4 mb-2" />
                  <div className="h-2 bg-surface-3 rounded w-1/2" />
                </div>
              ))}
            </div>
          ) : templates.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-gray-500 text-sm mb-2">No templates saved yet</p>
              <p className="text-gray-600 text-[11px]">Run an investigation, then click "Save TPL" in the toolbar to create a template</p>
            </div>
          ) : (
            templates.map(t => (
              <div key={t.id} className="bg-white/[0.02] rounded-lg overflow-hidden">
                <div className="flex items-center gap-2 px-3 py-2.5 group">
                  <button
                    onClick={() => handleUse(t)}
                    className="flex-1 text-left"
                  >
                    <div className="text-[13px] text-gray-200">{t.name}</div>
                    <div className="text-[11px] text-gray-500 mt-0.5">{t.description}</div>
                    {t.skills.length > 0 && (
                      <div className="flex gap-1 mt-1">
                        {t.skills.map(s => (
                          <span key={s} className="text-[9px] bg-accent-purple/10 text-accent-purple px-1.5 py-0.5 rounded">{s}</span>
                        ))}
                      </div>
                    )}
                  </button>
                  <button
                    onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}
                    className="opacity-0 group-hover:opacity-100 text-[10px] text-gray-500 hover:text-gray-300 px-1 transition-opacity"
                  >
                    {expandedId === t.id ? 'Hide' : 'Steps'}
                  </button>
                  <button
                    onClick={() => handleDelete(t.id)}
                    className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 px-1 transition-opacity"
                  >
                    {'\u2715'}
                  </button>
                </div>

                {expandedId === t.id && t.steps && (
                  <div className="px-3 pb-2.5 border-t border-white/[0.04]">
                    <div className="space-y-1 mt-2">
                      {t.steps.map((step, i) => (
                        <div key={i} className="text-[10px] text-gray-500 flex gap-2">
                          <span className="text-gray-600 tabular-nums w-4">{i + 1}.</span>
                          <span className="text-gray-400">{step.label}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        <div className="mt-4 pt-3 border-t border-surface-3 flex items-center justify-between text-[11px] text-gray-500">
          <span>Click a template to start an investigation</span>
          <div className="flex gap-2">
            <button
              onClick={() => {
                // Export all templates as JSON
                miscApi.listTemplates().then(data => {
                  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url; a.download = 'investigation-templates.json'; a.click()
                  URL.revokeObjectURL(url)
                })
              }}
              className="text-accent-blue hover:text-blue-400 transition-colors"
            >
              Export
            </button>
            <label className="text-accent-purple hover:text-purple-400 transition-colors cursor-pointer">
              Import
              <input type="file" accept=".json" className="hidden" onChange={(e) => {
                const file = e.target.files?.[0]
                if (!file) return
                const reader = new FileReader()
                reader.onload = () => {
                  try {
                    const imported = JSON.parse(reader.result as string)
                    const arr = Array.isArray(imported) ? imported : [imported]
                    Promise.all(arr.map((t: Record<string, unknown>) =>
                      miscApi.createTemplate(t)
                    )).then(() => {
                      // Refresh
                      miscApi.listTemplates().then(setTemplates)
                    })
                  } catch { /* ignore */ }
                }
                reader.readAsText(file)
                e.target.value = ''
              }} />
            </label>
          </div>
        </div>
      </div>
    </div>
  )
}
