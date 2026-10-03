import { useSyncExternalStore } from 'react'

// Stored in localStorage on purpose; see docs/adr/0001-jwt-in-localstorage.md.
const KEY = 'cs-analyze.token'
const listeners = new Set<() => void>()

function read(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export const tokenStore = {
  get: read,
  set(token: string | null) {
    try {
      if (token) localStorage.setItem(KEY, token)
      else localStorage.removeItem(KEY)
    } catch {
      // Storage unavailable (private mode, blocked site data): nothing to persist.
    }
    listeners.forEach((listener) => listener())
  },
  subscribe(listener: () => void) {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
}

export function useToken() {
  return useSyncExternalStore(tokenStore.subscribe, tokenStore.get)
}
