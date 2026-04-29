/**
 * Pure condition evaluator for playbook edge conditions.
 * All conditions on an edge must pass (AND logic) for the edge to be traversed.
 */

export interface PlaybookCondition {
  field: string
  operator: 'gt' | 'lt' | 'eq' | 'neq' | 'contains' | 'exists' | 'not_empty'
  value: unknown
}

/** Resolve a dot-path field from an object: 'rows[0].count' → obj.rows[0].count */
function resolveField(obj: Record<string, unknown>, path: string): unknown {
  let current: unknown = obj
  for (const part of path.replace(/\[(\d+)\]/g, '.$1').split('.')) {
    if (current == null || typeof current !== 'object') return undefined
    current = (current as Record<string, unknown>)[part]
  }
  return current
}

function evalCondition(output: Record<string, unknown>, cond: PlaybookCondition): boolean {
  const actual = resolveField(output, cond.field)

  switch (cond.operator) {
    case 'exists':
      return actual !== undefined && actual !== null
    case 'not_empty':
      if (Array.isArray(actual)) return actual.length > 0
      if (typeof actual === 'string') return actual.trim().length > 0
      return actual !== undefined && actual !== null
    case 'eq':
      return String(actual) === String(cond.value)
    case 'neq':
      return String(actual) !== String(cond.value)
    case 'gt':
      return Number(actual) > Number(cond.value)
    case 'lt':
      return Number(actual) < Number(cond.value)
    case 'contains':
      return String(actual).toLowerCase().includes(String(cond.value).toLowerCase())
    default:
      return false
  }
}

/** Evaluate all conditions on an edge. Returns true if ALL pass (AND logic). */
export function evaluateConditions(conditions: PlaybookCondition[] | undefined, output: Record<string, unknown>): boolean {
  if (!conditions || conditions.length === 0) return true
  return conditions.every(c => evalCondition(output, c))
}
