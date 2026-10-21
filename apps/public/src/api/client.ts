import createFetchClient, { type Middleware } from 'openapi-fetch'
import createClient from 'openapi-react-query'
import { tokenStore } from '../auth/token'
import type { paths } from './schema'

const auth: Middleware = {
  onRequest({ request }) {
    const token = tokenStore.get()
    if (token) request.headers.set('Authorization', `Bearer ${token}`)
    return request
  },
  onResponse({ response }) {
    // Expired token or Deactivated User: drop the token so the app falls back to the login page.
    if (response.status === 401 && tokenStore.get()) tokenStore.set(null)
    return response
  },
}

// OPS-8: a failed response's body always carries its status, so a page can
// tell a 404 from a server that didn't answer (Cloudflare's 52x is an HTML page).
const stamp: Middleware = {
  async onResponse({ response }) {
    if (response.ok || response.status === 401) return response
    let body: Record<string, unknown> = {}
    try {
      const parsed = await response.clone().json()
      if (parsed && typeof parsed === 'object') body = parsed
    } catch {
      body = { detail: response.statusText }
    }
    return new Response(JSON.stringify({ ...body, status: response.status }), {
      status: response.status,
      statusText: response.statusText,
      headers: { 'Content-Type': 'application/json' },
    })
  },
}

export const fetchClient = createFetchClient<paths>({ baseUrl: import.meta.env.VITE_API_URL })
fetchClient.use(auth, stamp)

export const $api = createClient(fetchClient)
