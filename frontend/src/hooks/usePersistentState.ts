import { useEffect, useState } from 'react'
import { readJSON, writeJSON } from '../lib/storage'

/** useState backed by localStorage (per-browser preferences only). */
export function usePersistentState<T>(key: string, initial: T): [T, (v: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => readJSON(key, initial))
  useEffect(() => writeJSON(key, value), [key, value])
  return [value, setValue]
}
