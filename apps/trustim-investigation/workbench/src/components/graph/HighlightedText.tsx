/** React component for search highlighting — no HTML string building */
export function HighlightedText({ text, search }: { text: string; search: string }) {
  if (!search.trim()) return <>{text}</>
  const parts = text.split(new RegExp(`(${search.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'))
  return (
    <>
      {parts.map((part, i) =>
        part.toLowerCase() === search.toLowerCase()
          ? <mark key={i} className="bg-yellow-500/40 text-yellow-200 rounded px-0.5">{part}</mark>
          : <span key={i}>{part}</span>
      )}
    </>
  )
}
