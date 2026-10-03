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

export const fetchClient = createFetchClient<paths>({ baseUrl: import.meta.env.VITE_API_URL })
fetchClient.use(auth)

export const $api = createClient(fetchClient)
