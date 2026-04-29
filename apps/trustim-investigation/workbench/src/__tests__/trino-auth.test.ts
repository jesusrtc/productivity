import { describe, it, expect } from 'vitest'
import { isTrinoAuthError } from '../utils/trino-auth'

describe('isTrinoAuthError', () => {
  it('detects "Authentication error: PasswordAuthenticator"', () => {
    expect(isTrinoAuthError('Authentication error: PasswordAuthenticator failed')).toBe(true)
  })

  it('detects "authentication failed for user"', () => {
    expect(isTrinoAuthError('authentication failed for user trustim')).toBe(true)
  })

  it('detects PasswordAuthenticator mention', () => {
    expect(isTrinoAuthError('Error from PasswordAuthenticator module')).toBe(true)
  })

  it('detects Kerberos failure', () => {
    expect(isTrinoAuthError('Kerberos ticket acquisition failed')).toBe(true)
  })

  it('detects access denied on Trino', () => {
    expect(isTrinoAuthError('access denied trino cluster')).toBe(true)
  })

  it('returns false for column not found errors', () => {
    expect(isTrinoAuthError('COLUMN_NOT_FOUND: column xyz')).toBe(false)
  })

  it('returns false for empty rows', () => {
    expect(isTrinoAuthError('Query returned 0 rows')).toBe(false)
  })

  it('returns false for empty string', () => {
    expect(isTrinoAuthError('')).toBe(false)
  })

  it('returns false for generic Trino errors without auth context', () => {
    expect(isTrinoAuthError('SYNTAX_ERROR: line 1:1: mismatched input')).toBe(false)
  })

  it('returns false for access denied without Trino context', () => {
    expect(isTrinoAuthError('access denied to resource')).toBe(false)
  })
})
