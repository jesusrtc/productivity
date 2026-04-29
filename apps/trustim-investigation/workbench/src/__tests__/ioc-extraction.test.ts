/**
 * Tests for extractIOCs from ioc-extraction.ts.
 * Extracts IPs, domains, hashes, and member IDs from text.
 */
import { describe, it, expect } from 'vitest'
import { extractIOCs } from '../utils/ioc-extraction'

describe('extractIOCs', () => {
  it('extracts IPv4 addresses', () => {
    const text = 'Traffic from 185.220.101.34 and 91.240.118.72 was flagged'
    const iocs = extractIOCs(text)
    expect(iocs).toContain('185.220.101.34')
    expect(iocs).toContain('91.240.118.72')
  })

  it('extracts domains with suspicious TLDs', () => {
    const text = 'Registrations used email domains ghksc.us and spam-domain.xyz'
    const iocs = extractIOCs(text)
    expect(iocs).toContain('ghksc.us')
    expect(iocs).toContain('spam-domain.xyz')
  })

  it('extracts member IDs (7+ digit numbers)', () => {
    const text = 'Affected members: 1234567 and 9876543210'
    const iocs = extractIOCs(text)
    expect(iocs).toContain('1234567')
    expect(iocs).toContain('9876543210')
  })

  it('returns empty array for empty text', () => {
    expect(extractIOCs('')).toEqual([])
  })

  it('deduplicates when same IOC appears twice', () => {
    const text = 'IP 185.220.101.34 seen again at 185.220.101.34'
    const iocs = extractIOCs(text)
    const ipCount = iocs.filter(i => i === '185.220.101.34').length
    expect(ipCount).toBe(1)
  })

  it('extracts hex hashes (32+ chars)', () => {
    const text = 'Hash: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4'
    const iocs = extractIOCs(text)
    expect(iocs).toContain('a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4')
  })

  it('extracts canvas hashes with 0x prefix', () => {
    const text = 'Canvas hash: 0xabcdef1234'
    const iocs = extractIOCs(text)
    expect(iocs).toContain('0xabcdef1234')
  })

  it('skips date-like numbers starting with 202', () => {
    const text = 'Date: 20250101 member: 1234567'
    const iocs = extractIOCs(text)
    expect(iocs).not.toContain('20250101')
    expect(iocs).toContain('1234567')
  })
})
