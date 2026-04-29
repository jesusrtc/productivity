/** Detect IOC overlap across different investigation branches */
export function detectConvergence(newNodeId: string, resultRaw: string, allNodes: Record<string, { node_id: string; result_raw: string; parent_ids: string[] }>) {
  if (!resultRaw || Object.keys(allNodes).length < 3) return

  // Extract IPs from new node
  const newIps = new Set((resultRaw.match(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g) || []))
  if (newIps.size === 0) return

  // Get the branch this node belongs to (ancestors)
  const getRoot = (id: string): string => {
    let cur = id
    const visited = new Set<string>()
    while ((allNodes[cur]?.parent_ids || [])[0] && !visited.has(cur)) {
      visited.add(cur)
      cur = (allNodes[cur].parent_ids || [])[0]
    }
    return cur
  }

  const newBranchRoot = getRoot(newNodeId)
  const overlaps: string[] = []

  for (const [otherId, other] of Object.entries(allNodes)) {
    if (otherId === newNodeId) continue
    if (getRoot(otherId) === newBranchRoot) continue // Same branch
    if (!other.result_raw) continue

    const otherIps = new Set((other.result_raw.match(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g) || []))
    for (const ip of newIps) {
      if (otherIps.has(ip)) { overlaps.push(ip); break }
    }
  }

  if (overlaps.length > 0) {
    import('../store/toast').then(({ useToastStore }) => {
      useToastStore.getState().addToast(
        `Convergence: ${overlaps.length} IP(s) found in multiple branches — consider synthesizing findings`,
        'info',
        6000
      )
    })
    import('../store/graph').then(({ useGraphStore }) => {
      useGraphStore.getState().addTag(newNodeId, 'convergence')
    })
  }
}
