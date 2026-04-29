/** Compute entry node IDs — nodes with no incoming edges */
export function computeEntryNodeIds(nodes: Array<{ id: string }>, edges: Array<{ target: string }>): string[] {
  const targets = new Set(edges.map(e => e.target))
  return nodes.filter(n => !targets.has(n.id)).map(n => n.id)
}
