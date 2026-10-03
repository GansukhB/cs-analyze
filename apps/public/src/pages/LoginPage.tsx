import { useState, type FormEvent } from 'react'
import { $api } from '../api/client'
import { tokenStore } from '../auth/token'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const login = $api.useMutation('post', '/auth/token', {
    onSuccess: (data) => tokenStore.set(data.access_token),
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    // OAuth2 password flow: the token endpoint takes a form, not JSON.
    login.mutate({
      body: { username, password, scope: '' },
      bodySerializer: (body) => new URLSearchParams(body as Record<string, string>),
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl border border-line bg-surface p-8">
        <h1 className="text-xl font-semibold text-ink">cs-analyze</h1>
        <label className="block space-y-1">
          <span className="text-sm text-ink-2">Username</span>
          <input
            className="w-full rounded-md border border-line bg-ground px-3 py-2 text-ink placeholder:text-ink-3 focus:border-ct focus:outline-none"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm text-ink-2">Password</span>
          <input
            className="w-full rounded-md border border-line bg-ground px-3 py-2 text-ink placeholder:text-ink-3 focus:border-ct focus:outline-none"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {login.isError && <p className="text-sm text-crit">Incorrect username or password.</p>}
        <button
          type="submit"
          disabled={login.isPending}
          className="w-full rounded-md bg-ct py-2 font-semibold text-ground hover:brightness-110 disabled:opacity-50"
        >
          {login.isPending ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}
