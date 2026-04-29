import { useState, useRef } from 'react'
import { useSessionStore } from '../../store/session'
import { useToastStore } from '../../store/toast'
import {
  exportSessionJson,
  exportSessionIpynb,
  generateSummary,
  exportGoogleDocsText,
  exportSlackMessage,
  exportPlaybookContribution,
  exportJiraTicketDraft,
  exportTimelineNarrative,
  generateAuditReport,
} from '../../utils/export'

interface Props {
  onClose: () => void
}

type ExportFormat = 'json' | 'ipynb' | 'summary' | 'playbook' | 'gdocs' | 'slack' | 'jira' | 'timeline' | 'audit'

const FORMAT_OPTIONS: { id: ExportFormat; label: string; desc: string }[] = [
  { id: 'json', label: 'Full JSON', desc: 'Graph + chat + all data' },
  { id: 'ipynb', label: 'Notebook', desc: 'Jupyter-compatible trace' },
  { id: 'audit', label: 'Audit Report', desc: 'Full audit with SEV + IOCs' },
  { id: 'summary', label: 'Summary', desc: 'Markdown summary' },
  { id: 'timeline', label: 'Timeline', desc: 'Chronological narrative' },
  { id: 'playbook', label: 'Playbook', desc: 'Decision path' },
  { id: 'gdocs', label: 'Google Docs', desc: 'Clean text' },
  { id: 'slack', label: 'Slack', desc: 'Paste to Slack' },
  { id: 'jira', label: 'Jira Ticket', desc: 'Jira wiki markup' },
]

export function ExportDialog({ onClose }: Props) {
  const [format, setFormat] = useState<ExportFormat>('json')
  const [preview, setPreview] = useState('')
  const [copied, setCopied] = useState(false)
  const importRef = useRef<HTMLInputElement>(null)

  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      try {
        const data = JSON.parse(reader.result as string)
        const session = data.session || data
        if (!session.id || !session.nodes) {
          useToastStore.getState().addToast('Invalid investigation file', 'error', 3000)
          return
        }
        useSessionStore.getState().loadSession(session, true)
        window.dispatchEvent(new CustomEvent('openInvestigationTab', { detail: { sessionId: session.id, name: session.name || 'Imported' } }))
        useToastStore.getState().addToast('Investigation imported', 'success', 3000)
        onClose()
      } catch {
        useToastStore.getState().addToast('Failed to parse file', 'error', 3000)
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  const getExportData = (): { content: string; filename: string; mimeType: string } | null => {
    const data = useSessionStore.getState().getSessionData()
    if (!data) return null

    switch (format) {
      case 'json':
        return {
          content: exportSessionJson(data),
          filename: `investigation-${data.id}.json`,
          mimeType: 'application/json',
        }
      case 'ipynb':
        return {
          content: exportSessionIpynb(data),
          filename: `investigation-${data.id}.ipynb`,
          mimeType: 'application/x-ipynb+json',
        }
      case 'summary':
        return {
          content: generateSummary(data),
          filename: `investigation-${data.id}-summary.md`,
          mimeType: 'text/markdown',
        }
      case 'playbook':
        return {
          content: exportPlaybookContribution(data),
          filename: `playbook-contribution-${data.id}.json`,
          mimeType: 'application/json',
        }
      case 'gdocs':
        return {
          content: exportGoogleDocsText(data),
          filename: `investigation-${data.id}.txt`,
          mimeType: 'text/plain',
        }
      case 'slack':
        return {
          content: exportSlackMessage(data),
          filename: `investigation-${data.id}-slack.txt`,
          mimeType: 'text/plain',
        }
      case 'jira':
        return {
          content: exportJiraTicketDraft(data),
          filename: `investigation-${data.id}-jira.txt`,
          mimeType: 'text/plain',
        }
      case 'timeline':
        return {
          content: exportTimelineNarrative(data),
          filename: `investigation-${data.id}-timeline.md`,
          mimeType: 'text/markdown',
        }
      case 'audit':
        return {
          content: generateAuditReport(data),
          filename: `investigation-${data.id}-audit.md`,
          mimeType: 'text/markdown',
        }
    }
  }

  const handleExport = () => {
    const result = getExportData()
    if (!result) return

    const blob = new Blob([result.content], { type: result.mimeType })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = result.filename
    a.click()
    URL.revokeObjectURL(url)
    useToastStore.getState().addToast(`Exported as ${result.filename}`, 'success', 3000)
  }

  const handlePreview = () => {
    const result = getExportData()
    if (!result) return
    const maxLen = format === 'summary' ? 10000 : 2000
    setPreview(
      result.content.length > maxLen
        ? result.content.slice(0, maxLen) + '\n...(truncated)'
        : result.content
    )
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[100]" onClick={onClose}>
      <div
        className="bg-surface-1 border border-surface-3 rounded-xl p-6 w-[640px] max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-medium text-gray-200 mb-4">Import / Export</h2>

        {/* Import + Export All */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => importRef.current?.click()}
            className="text-xs bg-surface-2 hover:bg-surface-3 text-gray-300 px-3 py-1.5 rounded-lg border border-surface-4 transition-colors"
          >
            Import Investigation File
          </button>
          <button
            onClick={() => window.open('/api/export/all', '_blank')}
            className="text-xs bg-surface-2 hover:bg-surface-3 text-gray-300 px-3 py-1.5 rounded-lg border border-surface-4 transition-colors"
          >
            Export All Sessions
          </button>
        </div>

        <div className="border-t border-surface-3 pt-4 mb-4">
          <h3 className="text-[12px] text-gray-500 uppercase tracking-wider mb-3">Export Current Investigation</h3>
        </div>

        {/* Format selector */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
          {FORMAT_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              onClick={() => { setFormat(opt.id); setPreview('') }}
              className={`text-left px-3 py-2 rounded-lg border transition-colors ${
                format === opt.id
                  ? 'border-accent-blue bg-accent-blue/10 text-gray-200'
                  : 'border-surface-3 bg-surface-2 text-gray-400 hover:border-surface-4'
              }`}
            >
              <div className="text-sm font-medium">{opt.label}</div>
              <div className="text-[10px]">{opt.desc}</div>
            </button>
          ))}
        </div>

        {/* Preview */}
        {preview && (
          <pre className="flex-1 bg-surface-0 rounded-lg p-3 text-xs text-gray-300 overflow-auto border border-surface-3 mb-4 max-h-[400px] whitespace-pre-wrap font-mono">
            {preview}
          </pre>
        )}

        {/* Actions */}
        <div className="flex gap-2 justify-end">
          <button
            onClick={handlePreview}
            className="text-xs text-gray-400 hover:text-gray-200 px-3 py-1.5 rounded hover:bg-surface-3 transition-colors"
          >
            Preview
          </button>
          <button
            onClick={() => {
              const result = getExportData()
              if (result) {
                navigator.clipboard.writeText(result.content)
                  .then(() => setCopied(true))
                  .then(() => setTimeout(() => setCopied(false), 2000))
              }
            }}
            className="text-xs text-gray-400 hover:text-gray-200 px-3 py-1.5 rounded hover:bg-surface-3 transition-colors"
          >
            {copied ? 'Copied!' : 'Copy to clipboard'}
          </button>
          <button onClick={onClose} className="text-xs text-gray-400 px-3 py-1.5">
            Cancel
          </button>
          <button
            onClick={handleExport}
            className="text-xs bg-accent-blue hover:bg-blue-600 text-white font-medium px-4 py-1.5 rounded-lg transition-colors"
          >
            Download {format.toUpperCase()}
          </button>
        </div>
        <input ref={importRef} type="file" accept=".json" onChange={handleImport} className="hidden" />
      </div>
    </div>
  )
}
