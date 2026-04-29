/**
 * Detects Trino authentication errors in query results.
 * Used by useChatAgentHandler to trigger the retry banner
 * and by tests to validate detection patterns.
 */
export function isTrinoAuthError(result: string): boolean {
  if (!result) return false
  const lower = result.toLowerCase()
  return lower.includes('authentication error') ||
    lower.includes('authentication failed') ||
    lower.includes('passwordauthenticator') ||
    (lower.includes('kerberos') && lower.includes('failed')) ||
    (lower.includes('access denied') && lower.includes('trino'))
}
