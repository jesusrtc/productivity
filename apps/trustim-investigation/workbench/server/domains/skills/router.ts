import { Router } from 'express'
import { sanitizeId } from '../../middleware/sanitize.js'
import { discoverSkills, readSkillContent } from './store.js'
import fs from 'fs'

export type { SkillMeta } from './store.js'

interface SkillsRouterConfig {
  SKILLS_DIR: string
}

/** Watch skills directory for changes, broadcasting events via WebSocket */
export function watchSkills(skillsDir: string, broadcast: (msg: object) => void) {
  if (!fs.existsSync(skillsDir)) return
  try {
    fs.watch(skillsDir, { recursive: true }, (eventType, filename) => {
      if (filename && (filename.endsWith('.md') || filename.endsWith('.yaml'))) {
        console.log(`Skill file changed: ${filename} (${eventType})`)
        broadcast({ type: 'skills_changed', payload: { file: filename, event: eventType } })
      }
    })
    console.log(`Watching skills directory for changes: ${skillsDir}`)
  } catch (err) {
    console.warn('Could not watch skills directory:', err)
  }
}

export default function createSkillsRouter(config: SkillsRouterConfig): Router {
  const router = Router()
  const { SKILLS_DIR } = config

  router.get('/', (_req, res) => {
    const skills = discoverSkills(SKILLS_DIR)
    res.json(skills)
  })

  router.get('/:name', (req, res) => {
    const skills = discoverSkills(SKILLS_DIR)
    const all = [...skills.investigation, ...skills.action]
    const skill = all.find((s) => s.name === sanitizeId(req.params.name))
    if (!skill) {
      res.status(404).json({ error: 'Skill not found' })
      return
    }
    const content = readSkillContent(skill.file_path)
    res.json({ ...skill, content })
  })

  return router
}
