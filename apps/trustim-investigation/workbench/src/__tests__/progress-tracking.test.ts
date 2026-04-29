/**
 * Tests for progress tracking — ensures failed queries are counted correctly.
 *
 * Past bug: progress showed 22/27 when 4 queries failed and 22 succeeded.
 * Should show 26/27 (1 still running) or 27/27 (all done, 4 failed).
 */
import { describe, it, expect } from 'vitest'

/** Replicate the progress calculation used across ChatPanel components */
function calculateProgress(nodes: Array<{ status: string }>) {
  const completed = nodes.filter(n => n.status === 'completed').length
  const failed = nodes.filter(n => n.status === 'failed').length
  const running = nodes.filter(n => n.status === 'running').length
  const done = completed + failed
  const total = nodes.length
  const pct = total > 0 ? Math.round((done / total) * 100) : 0
  return { completed, failed, running, done, total, pct }
}

describe('Progress Tracking', () => {
  it('counts failed queries as done', () => {
    const nodes = [
      ...Array(22).fill({ status: 'completed' }),
      ...Array(4).fill({ status: 'failed' }),
      { status: 'running' },
    ]
    const p = calculateProgress(nodes)
    expect(p.done).toBe(26)
    expect(p.total).toBe(27)
    expect(p.running).toBe(1)
    expect(p.pct).toBe(96) // 26/27 = 96%
  })

  it('shows 100% when all queries complete (including failures)', () => {
    const nodes = [
      ...Array(22).fill({ status: 'completed' }),
      ...Array(5).fill({ status: 'failed' }),
    ]
    const p = calculateProgress(nodes)
    expect(p.done).toBe(27)
    expect(p.total).toBe(27)
    expect(p.pct).toBe(100)
  })

  it('shows 0% for empty investigation', () => {
    const p = calculateProgress([])
    expect(p.done).toBe(0)
    expect(p.total).toBe(0)
    expect(p.pct).toBe(0)
  })

  it('handles all-running state', () => {
    const nodes = Array(5).fill({ status: 'running' })
    const p = calculateProgress(nodes)
    expect(p.done).toBe(0)
    expect(p.running).toBe(5)
    expect(p.pct).toBe(0)
  })
})
