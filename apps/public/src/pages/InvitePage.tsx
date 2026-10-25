// The one page a person sees before they have an account (docs/plans/01 WS-3):
// a Staff member's link, opened once, makes their login (or sets a forgotten
// password) and signs them in.
import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router'
import { $api } from '../api/client'
import { tokenStore } from '../auth/token'

const input =
  'w-full rounded-md border border-line bg-ground px-3 py-2 text-ink placeholder:text-ink-3 focus:border-ct focus:outline-none'

export default function InvitePage({ token }: { token: string }) {
  const navigate = useNavigate()
  const invite = $api.useQuery('get', '/invites/{token}', { params: { path: { token } } })
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [repeat, setRepeat] = useState('')
  const accept = $api.useMutation('post', '/invites/{token}/accept', {
    onSuccess: (data) => {
      tokenStore.set(data.access_token)
      navigate('/', { replace: true })
    },
  })
  const reset = Boolean(invite.data?.username)

  function submit(event: FormEvent) {
    event.preventDefault()
    if (password !== repeat) return
    accept.mutate({ params: { path: { token } }, body: { username, password } })
  }

  const error = (accept.error as { detail?: string } | undefined)?.detail
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-4 rounded-xl border border-line bg-surface p-8">
        <h1 className="text-xl font-semibold text-ink">cs-analyze</h1>
        {invite.isError ? (
          <p className="text-ink-2">Энэ урилга ашиглагдсан, хугацаа нь дууссан эсвэл буруу байна. Staff-аас шинийг аваарай.</p>
        ) : !invite.data ? (
          <p className="text-ink-3">Уншиж байна…</p>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <p className="text-sm text-ink-2">
              {reset ? (
                <>
                  <b className="text-ink">{invite.data.username}</b>-ийн шинэ нууц үг ({invite.data.workspace}).
                </>
              ) : (
                <>
                  <b className="text-ink">{invite.data.workspace}</b>-д{' '}
                  {invite.data.role === 'player' ? `тоглогч ${invite.data.player}` : 'Staff'} болж нэгдэх.
                </>
              )}
            </p>
            {!reset && (
              <label className="block space-y-1">
                <span className="text-sm text-ink-2">Username</span>
                <input
                  className={input}
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  pattern="[A-Za-z0-9_.\-]{3,32}"
                  required
                />
              </label>
            )}
            <label className="block space-y-1">
              <span className="text-sm text-ink-2">Нууц үг (6+ тэмдэгт)</span>
              <input
                className={input}
                type="password"
                autoComplete="new-password"
                minLength={6}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
            <label className="block space-y-1">
              <span className="text-sm text-ink-2">Дахин</span>
              <input
                className={input}
                type="password"
                autoComplete="new-password"
                value={repeat}
                onChange={(e) => setRepeat(e.target.value)}
                required
              />
            </label>
            {repeat && password !== repeat && <p className="text-sm text-warn">Нууц үг таарахгүй байна.</p>}
            {error && <p className="text-sm text-crit">{error}</p>}
            <button
              type="submit"
              disabled={accept.isPending}
              className="w-full rounded-md bg-ct px-4 py-2 font-medium text-ground hover:opacity-90 disabled:opacity-50"
            >
              {reset ? 'Нууц үг солих' : 'Нэгдэх'}
            </button>
          </form>
        )}
      </div>
    </main>
  )
}
