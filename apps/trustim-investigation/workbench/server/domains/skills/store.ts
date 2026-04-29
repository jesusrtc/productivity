import fs from 'fs'
import path from 'path'

export interface SkillMeta {
  name: string
  description: string
  allowed_tools: string[]
  file_path: string
  category: 'investigation' | 'action'
  area: string
}

export function discoverSkills(skillsDir: string): { investigation: SkillMeta[]; action: SkillMeta[] } {
  const result: { investigation: SkillMeta[]; action: SkillMeta[] } = {
    investigation: [],
    action: [],
  }

  if (!fs.existsSync(skillsDir)) return result

  const entries = fs.readdirSync(skillsDir, { withFileTypes: true })
  for (const entry of entries) {
    if (!entry.isDirectory()) continue

    if (entry.name === 'actions') {
      const actionsDir = path.join(skillsDir, 'actions')
      const actionEntries = fs.readdirSync(actionsDir, { withFileTypes: true })
      for (const ae of actionEntries) {
        if (!ae.isDirectory()) continue
        const skillFile = path.join(actionsDir, ae.name, 'SKILL.md')
        if (fs.existsSync(skillFile)) {
          const meta = parseSkillFrontmatter(skillFile, 'action', ae.name)
          if (meta) result.action.push(meta)
        }
      }
    } else {
      const skillFile = path.join(skillsDir, entry.name, 'SKILL.md')
      if (fs.existsSync(skillFile)) {
        const meta = parseSkillFrontmatter(skillFile, 'investigation', entry.name)
        if (meta) result.investigation.push(meta)
      }
    }
  }

  return result
}

export function parseSkillFrontmatter(filePath: string, category: 'investigation' | 'action', dirName: string): SkillMeta | null {
  const content = fs.readFileSync(filePath, 'utf-8')
  const fmMatch = content.match(/^---\n([\s\S]*?)\n---/)
  if (!fmMatch) {
    return {
      name: dirName,
      description: '',
      allowed_tools: [],
      file_path: filePath,
      category,
      area: dirName,
    }
  }

  const fm = fmMatch[1]
  const name = fm.match(/name:\s*(.+)/)?.[1]?.trim() || dirName
  const descMatch = fm.match(/description:\s*>-?\s*\n([\s\S]*?)(?=\n\w|\n---)/)?.[1]?.trim()
    || fm.match(/description:\s*(.+)/)?.[1]?.trim()
    || ''
  const tools = fm.match(/allowed-tools:\s*(.+)/)?.[1]?.trim() || ''

  return {
    name,
    description: descMatch.replace(/\n\s+/g, ' '),
    allowed_tools: tools.split(',').map((t) => t.trim()).filter(Boolean),
    file_path: filePath,
    category,
    area: dirName,
  }
}

export function readSkillContent(filePath: string): string {
  return fs.readFileSync(filePath, 'utf-8')
}
