import { useCallback } from 'react'
import { useSessionStore } from '../store/session'
import { miscApi } from '../api'
import { routeInvestigationWithConfidence } from '../utils/investigation-router'
import { v4 as uuid } from 'uuid'
import type { InvestigationNode } from '../types'
import type { ChatMessage, MessageRole } from '../types/session'

interface UseChatFirstMessageConfig {
  addNode: (data: Partial<InvestigationNode> & { node_id?: string }) => string
  addMessage: (role: MessageRole, content: string, extras?: Partial<ChatMessage>) => string
  lastCompletedNodeRef: React.MutableRefObject<string | null>
  firstMessageRootRef: React.MutableRefObject<string | null>
  pendingAutoInvestigateRef: React.MutableRefObject<boolean>
}

export function useChatFirstMessage(config: UseChatFirstMessageConfig) {
  const { addNode, addMessage, lastCompletedNodeRef, firstMessageRootRef, pendingAutoInvestigateRef } = config

  const handleFirstMessage = useCallback((content: string) => {
    // Auto-detect investigation type from prompt with confidence scoring
    const routeResult = routeInvestigationWithConfidence(content)
    const route = routeResult?.route || null
    const sessionName = route
      ? `${route.category}: ${content.slice(0, 40)}`
      : content.slice(0, 60)
    useSessionStore.getState().renameSession(sessionName)

    if (route && routeResult) {
      const confLabel = routeResult.confidence === 'high' ? '' : routeResult.confidence === 'medium' ? ' (moderate match)' : ' (weak match — verify)'
      addMessage('system', `Detected investigation type: **${route.description}** (skill: ${route.skill})${confLabel}`)
      useSessionStore.getState().recordSkillUsed(route.skill)

      // Fetch skill key tables for context
      miscApi.getSkill(route.skill)
        .then((skill: any) => {
          if (skill.content) {
            const tableMatches = skill.content.match(/\| `([^`]+)` \|/g)
            if (tableMatches && tableMatches.length > 0) {
              const tables = tableMatches.map((m: string) => m.match(/`([^`]+)`/)?.[1]).filter(Boolean).slice(0, 5)
              if (tables.length > 0) {
                addMessage('system', `Key tables: ${tables.map((t: string) => `\`${t}\``).join(', ')}`)
              }
            }
          }
        })
        .catch(() => {})
    }

    // Check for matching templates
    if (route) {
      miscApi.listTemplates()
        .then((templates: any) => {
          const matching = templates.filter((t: any) => t.skills.includes(route.skill))
          if (matching.length > 0) {
            addMessage('system', `Template available: "${matching[0].name}" — use Templates panel to apply.`)
          }
        })
        .catch(() => {})
    }

    // Detect alert/incident IDs and add context hints
    const alertMatch = content.match(/\balert\s*#?\s*(\d{6,})/i)
    const incidentMatch = content.match(/\bincident\s*#?\s*(\d{6,})/i)
    if (alertMatch) {
      addMessage('system', `Alert ID **${alertMatch[1]}** detected. The agent will fetch context from InResponse via \`ir alert view ${alertMatch[1]}\`.`)
    } else if (incidentMatch) {
      addMessage('system', `Incident ID **${incidentMatch[1]}** detected. The agent will fetch context from InResponse.`)
    }

    // Detect member IDs in the prompt
    const midMatch = content.match(/\b(\d{7,12})\b/g)
    if (midMatch && midMatch.length > 0 && !alertMatch && !incidentMatch) {
      const mids = [...new Set(midMatch.filter(m => !m.startsWith('202')))].slice(0, 5)
      if (mids.length > 0) {
        addMessage('system', `Detected ${mids.length} member ID(s): ${mids.join(', ')}`)
      }
    }

    // Create the root node — the user's prompt IS the root of the investigation tree
    const rootId = addNode({
      node_id: uuid(),
      action_type: route ? 'skill_invocation' : 'enrichment',
      label: content.slice(0, 80),
      query: content,
      skill_name: route?.skill || null,
      status: 'completed',
      result_summary: 'Investigation started by investigator',
      result_raw: content,
      reasoning: 'Root node: investigator prompt',
      confidence: 0,
    } as any)
    lastCompletedNodeRef.current = rootId
    firstMessageRootRef.current = rootId

    // Auto-investigate will start when Claude's first turn completes (handled in the `done` case
    // of handleAgentEvent). This replaces the previous setTimeout(20000) which could preempt
    // Claude mid-response.
    pendingAutoInvestigateRef.current = true
  }, [addNode, addMessage, lastCompletedNodeRef, firstMessageRootRef, pendingAutoInvestigateRef])

  return { handleFirstMessage }
}
