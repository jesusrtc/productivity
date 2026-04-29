interface ContextBreadcrumbProps {
  nodeId: string
  nodes: Record<string, { label: string; parent_ids: string[] }>
  onNavigate: (id: string) => void
}

/** Breadcrumb trail from root to the current context node */
export function ContextBreadcrumb({ nodeId, nodes, onNavigate }: ContextBreadcrumbProps) {
  // Walk up to root
  const path: string[] = []
  const visited = new Set<string>()
  let cur = nodeId
  while (cur && !visited.has(cur) && nodes[cur]) {
    visited.add(cur)
    path.unshift(cur)
    cur = (nodes[cur].parent_ids || [])[0]
  }

  if (path.length <= 1) return null

  // Show at most 5 items: first, ..., last 3, current
  const display = path.length <= 5 ? path : [path[0], '...', ...path.slice(-3)]

  return (
    <div className="flex items-center gap-1 ml-3.5 mb-1 flex-wrap">
      {display.map((id, i) => {
        if (id === '...') {
          return <span key="ellipsis" className="text-[10px] text-gray-600">{'\u2026'}</span>
        }
        const node = nodes[id]
        const isLast = i === display.length - 1
        return (
          <span key={id} className="flex items-center gap-1">
            {i > 0 && id !== '...' && <span className="text-[10px] text-gray-600">{'\u203A'}</span>}
            <button
              onClick={() => onNavigate(id)}
              className={`text-[10px] truncate max-w-[100px] transition-colors ${
                isLast ? 'text-accent-blue font-medium' : 'text-gray-500 hover:text-gray-300'
              }`}
              title={node?.label}
            >
              {node?.label?.slice(0, 20) || id.slice(0, 8)}
            </button>
          </span>
        )
      })}
    </div>
  )
}
