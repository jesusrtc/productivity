import { useState, useRef, useEffect } from 'react'

/** Live elapsed timer for processing indicator */
export function LiveElapsed() {
  const [elapsed, setElapsed] = useState(0)
  const startRef = useRef(Date.now())
  useEffect(() => {
    startRef.current = Date.now()
    const interval = setInterval(() => setElapsed(Math.floor((Date.now() - startRef.current) / 1000)), 1000)
    return () => clearInterval(interval)
  }, [])
  return <span className="text-[10px] text-gray-500 tabular-nums">{elapsed}s</span>
}
