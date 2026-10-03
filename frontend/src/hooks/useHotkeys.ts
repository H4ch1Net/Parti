import { useEffect, useRef } from 'react'

export type HotkeyMap = Record<string, (e: KeyboardEvent) => void>

function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
}

/**
 * Global shortcuts. Keys are matched against `event.key`; prefix with
 * "mod+" for Ctrl/Cmd combos, which also fire while typing.
 */
export function useHotkeys(map: HotkeyMap): void {
  const ref = useRef(map)
  ref.current = map
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey
      const key = (mod ? 'mod+' : '') + e.key
      const handler = ref.current[key]
      if (!handler) return
      if (!mod && (isTyping(e.target) || e.altKey)) return
      e.preventDefault()
      handler(e)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}
