import { useQueryClient } from '@tanstack/react-query'
import { NavLink, Outlet, useMatch } from 'react-router'
import { $api } from './api/client'
import Assistant from './assistant/Assistant'
import { tokenStore } from './auth/token'

const link = ({ isActive }: { isActive: boolean }) =>
  isActive ? 'text-ink' : 'text-ink-3 hover:text-ink'

export default function Layout() {
  const queryClient = useQueryClient()
  const me = $api.useQuery('get', '/auth/me')
  // A match page holds a Replay beside its Round panel: it gets the screen's width.
  const width = useMatch('/matches/*') ? 'max-w-[1680px]' : 'max-w-5xl'

  function logout() {
    tokenStore.set(null)
    queryClient.clear()
  }

  return (
    <>
      <header className="border-b border-line bg-surface">
        <div className={`mx-auto flex ${width} flex-wrap items-center gap-6 px-4 py-3 text-sm`}>
          <span className="font-semibold text-ink">cs-analyze</span>
          <nav className="flex gap-4">
            <NavLink to="/" end className={link}>
              New analysis
            </NavLink>
            <NavLink to="/jobs" className={link}>
              Jobs
            </NavLink>
            <NavLink to="/teams" className={link}>
              Teams
            </NavLink>
            <NavLink to="/gameplan" className={link}>
              Game plan
            </NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-4">
            {me.data && <span className="text-ink-3">{me.data.username}</span>}
            <button onClick={logout} className="text-ink-3 underline hover:text-ink">
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className={`mx-auto ${width} px-4 py-8`}>
        <Outlet />
      </main>
      <Assistant />
    </>
  )
}
