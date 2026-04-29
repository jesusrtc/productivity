import path from 'path'

/** Sanitize user-provided ID to prevent path traversal */
export function sanitizeId(id: string): string {
  return id.replace(/[^a-zA-Z0-9_-]/g, '')
}

/** Resolve a file path within a base directory, rejecting traversal attempts */
export function safePath(baseDir: string, ...segments: string[]): string | null {
  const resolved = path.resolve(baseDir, ...segments)
  if (!resolved.startsWith(path.resolve(baseDir))) return null
  return resolved
}
