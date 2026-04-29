import { INVESTIGATION_DIMENSIONS } from '../data/investigation-dimensions'

/** Check which investigation dimensions haven't been covered yet */
export function getUncoveredDimensions(nodes: Record<string, { label: string; query: string; tags: string[] }>): string[] {
  const texts = Object.values(nodes).map(n => [n.label, n.query, ...(n.tags || [])].join(' ').toLowerCase())
  return INVESTIGATION_DIMENSIONS
    .filter(d => !texts.some(t => d.keywords.some(kw => t.includes(kw))))
    .map(d => d.label)
}
