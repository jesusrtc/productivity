import { useState, useRef, useEffect, useMemo } from 'react'
import { miscApi } from '../../api'
import type { Skill } from '../../types'

interface Props {
  onSend: (content: string) => void
  disabled?: boolean
}

export function ChatInput({ onSend, disabled }: Props) {
  const [value, setValue] = useState('')
  const [skills, setSkills] = useState<Skill[]>([])
  const [showAutocomplete, setShowAutocomplete] = useState(false)
  const [selectedIdx, setSelectedIdx] = useState(0)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Listen for prefill events (from table cell double-click, etc.)
  useEffect(() => {
    const handler = (e: Event) => {
      const text = (e as CustomEvent).detail?.text
      if (text) {
        setValue(text)
        textareaRef.current?.focus()
      }
    }
    window.addEventListener('prefillChat', handler)
    return () => window.removeEventListener('prefillChat', handler)
  }, [])

  // Load skills for autocomplete
  useEffect(() => {
    miscApi.listSkills()
      .then((data: any) => setSkills([...data.investigation, ...data.action]))
      .catch(() => {})
  }, [])

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 200) + 'px'
    }
  }, [value])

  // Skill autocomplete: detect /prefix at start of input
  const slashPrefix = useMemo(() => {
    const match = value.match(/^\/(\S*)$/)
    return match ? match[1].toLowerCase() : null
  }, [value])

  const filteredSkills = useMemo(() => {
    if (slashPrefix === null) return []
    if (slashPrefix === '') return skills.slice(0, 8)
    return skills.filter((s) => s.name.toLowerCase().includes(slashPrefix)).slice(0, 8)
  }, [slashPrefix, skills])

  useEffect(() => {
    setShowAutocomplete(filteredSkills.length > 0 && slashPrefix !== null)
    setSelectedIdx(0)
  }, [filteredSkills, slashPrefix])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Autocomplete navigation
    if (showAutocomplete) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIdx((i) => Math.min(i + 1, filteredSkills.length - 1))
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIdx((i) => Math.max(i - 1, 0))
        return
      }
      if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
        e.preventDefault()
        const skill = filteredSkills[selectedIdx]
        if (skill) {
          setValue(`/${skill.name} `)
          setShowAutocomplete(false)
        }
        return
      }
      if (e.key === 'Escape') {
        setShowAutocomplete(false)
        return
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (value.trim() && !disabled) {
        onSend(value.trim())
        setValue('')
      }
    }
  }

  return (
    <div className="border-t border-surface-3 p-3 flex-shrink-0 relative">
      {/* Skill autocomplete dropdown (R43) */}
      {/* Apple HIG: Autocomplete with vibrancy and generous spacing */}
      {showAutocomplete && (
        <div className="absolute bottom-full left-3 right-3 mb-2 glass-panel rounded-xl shadow-2xl overflow-hidden z-20">
          {filteredSkills.map((skill, i) => (
            <button
              key={skill.name}
              onClick={() => {
                setValue(`/${skill.name} `)
                setShowAutocomplete(false)
                textareaRef.current?.focus()
              }}
              className={`w-full text-left px-4 py-2.5 text-[13px] transition-all ${
                i === selectedIdx ? 'bg-accent-blue/15 text-gray-100' : 'text-gray-300 hover:bg-white/[0.04]'
              }`}
            >
              <span className="text-accent-purple font-semibold">/{skill.name}</span>
              {skill.description && (
                <span className="text-gray-500 ml-2">{skill.description.slice(0, 55)}</span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Apple HIG: Clean input area with generous padding */}
      <div className="flex gap-2.5">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          aria-label="Investigation prompt"
          role="textbox"
          placeholder="Type a message, paste an IOC, or type / for skills..."
          disabled={disabled}
          className="flex-1 bg-surface-2/60 border border-white/[0.06] rounded-xl px-4 py-2.5 text-[15px] text-gray-100 placeholder-gray-500 focus:border-accent-blue/50 focus:ring-2 focus:ring-accent-blue/15 focus:outline-none resize-none min-h-[42px] max-h-[200px] disabled:opacity-40 transition-all"
          rows={1}
        />
        <button
          onClick={() => {
            if (value.trim() && !disabled) {
              onSend(value.trim())
              setValue('')
            }
          }}
          disabled={!value.trim() || disabled}
          className="self-end bg-accent-blue hover:bg-blue-500 disabled:bg-white/[0.04] disabled:text-gray-600 text-white text-[14px] font-semibold px-5 py-2.5 rounded-xl transition-all active:scale-[0.96] shadow-lg shadow-accent-blue/20 disabled:shadow-none"
        >
          Send
        </button>
      </div>
      <div className="flex items-center gap-4 mt-2 text-[11px] text-gray-500/70">
        <span>Return to send</span>
        <span>/ for skills</span>
        <span>#note to annotate</span>
        <button
          onClick={() => {
            const today = new Date().toISOString().split('T')[0]
            setValue(prev => prev + (prev.endsWith(' ') || !prev ? '' : ' ') + today)
            textareaRef.current?.focus()
          }}
          className="text-gray-600 hover:text-gray-400 transition-colors"
          title={`Insert today's date: ${new Date().toISOString().split('T')[0]}`}
        >
          {new Date().toISOString().split('T')[0]}
        </button>
      </div>
    </div>
  )
}
