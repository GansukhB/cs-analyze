// The Workspace's people (docs/plans/01 WS-3): Staff invite Staff or a Player by a
// one-time link, tie a Player login to its Player, deactivate, and send a reset
// link for a forgotten password. The link is shown once: only its hash is stored.
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { $api } from '../api/client'
import type { components } from '../api/schema'
import { useMe, useMyTeams } from '../auth/useMe'
import { day } from '../jobs/format'

type Member = components['schemas']['MemberRead']

const linkOf = (token: string) => `${window.location.origin}/invite/${token}`

export default function WorkspacePage() {
  const me = useMe()
  const myTeams = useMyTeams()
  const list = $api.useQuery('get', '/workspace/members')
  const [link, setLink] = useState<{ url: string; what: string } | null>(null)
  if (list.isError) return <p className="text-crit">Гишүүдийг уншиж чадсангүй.</p>
  if (!list.data) return <p className="text-ink-3">Уншиж байна…</p>

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold text-ink">{me.data?.workspace.name ?? 'Workspace'}</h1>
        <p className="text-ink-2">
          My team: {myTeams.map((t) => t.name + (t.label ? ` (${t.label})` : '')).join(', ') || '—'}
        </p>
      </div>

      <InviteForm onLink={setLink} />
      {link && (
        <div className="space-y-2 rounded-xl border border-ct bg-surface p-4 text-sm">
          <p className="text-ink-2">
            {link.what}: энэ линкийг нэг удаа, 7 хоногийн дотор ашиглана. Дахин харагдахгүй тул одоо хуулж аваарай.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <code className="break-all rounded bg-ground px-2 py-1 font-mono text-xs text-ink">{link.url}</code>
            <button
              type="button"
              onClick={() => navigator.clipboard?.writeText(link.url)}
              className="rounded-md border border-line px-3 py-1 text-xs text-ink hover:border-ink-3"
            >
              Хуулах
            </button>
          </div>
        </div>
      )}

      <section className="space-y-3">
        <h2 className="font-medium text-ink">Гишүүд</h2>
        <div className="overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full text-sm">
            <thead className="border-b border-line text-left text-xs uppercase text-ink-3">
              <tr>
                <th className="px-4 py-2">Username</th>
                <th className="px-4 py-2">Эрх</th>
                <th className="px-4 py-2">Тоглогч</th>
                <th className="px-4 py-2">Сүүлд нэвтэрсэн</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {list.data.members.map((m) => (
                <MemberRow key={m.id} member={m} self={m.id === me.data?.id} onLink={setLink} />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {list.data.invites.length > 0 && (
        <section className="space-y-3">
          <h2 className="font-medium text-ink">Нээлттэй урилга</h2>
          <ul className="space-y-2 text-sm">
            {list.data.invites.map((i) => (
              <OpenInvite key={i.id} invite={i} />
            ))}
          </ul>
        </section>
      )}
      <Disputes />
    </div>
  )
}

/** How often each Finding code is disputed (RV-7): a detector's only real feedback. */
function Disputes() {
  const rates = $api.useQuery('get', '/workspace/disputes')
  if (!rates.data?.length) return null
  return (
    <section className="space-y-2">
      <h2 className="font-medium text-ink">Маргасан Finding</h2>
      <p className="max-w-2xl text-sm text-ink-3">
        Review дээр «Буруу?» гэж тэмдэглэсэн Finding, кодоор. Давтамж өндөр кодын босгыг дахин харах хэрэгтэй.
      </p>
      <table className="text-sm">
        <thead className="text-left text-xs text-ink-3">
          <tr>
            <th className="py-1 pr-6 font-normal">Finding</th>
            <th className="py-1 pr-6 text-right font-normal">Маргасан</th>
            <th className="py-1 pr-6 text-right font-normal">Нийт</th>
            <th className="py-1 pr-6 text-right font-normal">Хувь</th>
            <th className="py-1 font-normal">Шалтгаан</th>
          </tr>
        </thead>
        <tbody className="text-ink-2">
          {rates.data.map((r) => (
            <tr key={r.code} className="border-t-1 border-line">
              <td className="py-1 pr-6 text-ink">{r.label}</td>
              <td className="py-1 pr-6 text-right font-mono">{r.disputes}</td>
              <td className="py-1 pr-6 text-right font-mono">{r.findings}</td>
              <td className="py-1 pr-6 text-right font-mono">{r.rate == null ? '—' : `${(r.rate * 100).toFixed(1)}%`}</td>
              <td className="py-1 text-xs text-ink-3">
                {Object.entries(r.reasons)
                  .map(([k, n]) => `${k} ${n}`)
                  .join(', ')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function useRefresh() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ['get', '/workspace/members'] })
}

function InviteForm({ onLink }: { onLink: (l: { url: string; what: string }) => void }) {
  const refresh = useRefresh()
  const [role, setRole] = useState<'staff' | 'player'>('player')
  const [q, setQ] = useState('')
  const [player, setPlayer] = useState<{ steamid: string; name: string } | null>(null)
  const found = $api.useQuery(
    'get',
    '/gameplan/players',
    { params: { query: { q } } },
    { enabled: role === 'player' && q.trim().length >= 2 && !player },
  )
  const make = $api.useMutation('post', '/workspace/invites', {
    onSuccess: (data) => {
      onLink({ url: linkOf(data.token), what: data.player ? `${data.player.name}-ийн урилга` : 'Staff-ийн урилга' })
      setPlayer(null)
      setQ('')
      refresh()
    },
  })
  const error = (make.error as { detail?: string } | undefined)?.detail
  return (
    <section className="space-y-3 rounded-xl border border-line bg-surface p-4 text-sm">
      <h2 className="font-medium text-ink">Урих</h2>
      <div className="flex flex-wrap items-center gap-4">
        {(['player', 'staff'] as const).map((r) => (
          <label key={r} className="flex items-center gap-2 text-ink-2">
            <input type="radio" checked={role === r} onChange={() => setRole(r)} />
            {r === 'player' ? 'Тоглогч' : 'Staff'}
          </label>
        ))}
      </div>
      {role === 'player' && (
        <div className="space-y-2">
          {player ? (
            <p className="text-ink">
              {player.name}{' '}
              <button type="button" onClick={() => setPlayer(null)} className="text-xs text-ink-3 underline">
                солих
              </button>
            </p>
          ) : (
            <>
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Тоглогчийн нэр"
                className="w-full max-w-sm rounded-md border border-line bg-surface-2 px-3 py-2 text-ink"
              />
              <ul className="space-y-1">
                {(found.data?.players ?? []).slice(0, 8).map((p) => (
                  <li key={p.steamid}>
                    <button
                      type="button"
                      onClick={() => setPlayer({ steamid: p.steamid, name: p.name })}
                      className="text-ct hover:underline"
                    >
                      {p.name}
                    </button>{' '}
                    <span className="text-xs text-ink-3">{p.team}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
      <button
        type="button"
        disabled={make.isPending || (role === 'player' && !player)}
        onClick={() => make.mutate({ body: { role, player_steamid: player?.steamid ?? null } })}
        className="rounded-md border border-line bg-raised px-4 py-2 text-ink hover:border-ink-3 disabled:opacity-50"
      >
        Урилгын линк үүсгэх
      </button>
      {error && <p className="text-crit">{error}</p>}
    </section>
  )
}

function MemberRow({
  member: m,
  self,
  onLink,
}: {
  member: Member
  self: boolean
  onLink: (l: { url: string; what: string }) => void
}) {
  const refresh = useRefresh()
  const change = $api.useMutation('patch', '/workspace/members/{member_id}', { onSuccess: refresh })
  const reset = $api.useMutation('post', '/workspace/invites', {
    onSuccess: (data) => {
      onLink({ url: linkOf(data.token), what: `${m.username}-ийн нууц үг сэргээх линк` })
      refresh()
    },
  })
  const error = (change.error as { detail?: string } | undefined)?.detail
  return (
    <tr className={`border-b border-line-soft last:border-0 ${m.is_active ? '' : 'text-ink-3'}`}>
      <td className="px-4 py-2">
        {m.username}
        {self && <span className="ml-2 text-xs text-ink-3">(та)</span>}
        {!m.is_active && <span className="ml-2 text-xs">идэвхгүй</span>}
      </td>
      <td className="px-4 py-2">{m.role === 'staff' ? 'Staff' : 'Тоглогч'}</td>
      <td className="px-4 py-2">{m.player?.name ?? '—'}</td>
      <td className="px-4 py-2 text-ink-3">{day(m.last_login_at)}</td>
      <td className="px-4 py-2 text-right text-xs whitespace-nowrap">
        {!self && (
          <button
            type="button"
            onClick={() =>
              change.mutate({ params: { path: { member_id: m.id } }, body: { is_active: !m.is_active } })
            }
            className="mr-3 text-ink-3 underline hover:text-ink"
          >
            {m.is_active ? 'Идэвхгүй болгох' : 'Идэвхжүүлэх'}
          </button>
        )}
        <button
          type="button"
          onClick={() => reset.mutate({ body: { role: 'staff', user_id: m.id } })}
          className="text-ink-3 underline hover:text-ink"
        >
          Нууц үг сэргээх линк
        </button>
        {error && <span className="ml-2 text-crit">{error}</span>}
      </td>
    </tr>
  )
}

function OpenInvite({ invite: i }: { invite: components['schemas']['InviteRead'] }) {
  const refresh = useRefresh()
  const revoke = $api.useMutation('delete', '/workspace/invites/{invite_id}', { onSuccess: refresh })
  const what = i.username
    ? `${i.username}: нууц үг сэргээх`
    : i.role === 'player'
      ? `Тоглогч ${i.player?.name ?? ''}`
      : 'Staff'
  return (
    <li className="flex flex-wrap items-center gap-3 rounded-md border border-line-soft bg-surface px-3 py-2">
      <span className="text-ink">{what}</span>
      <span className="text-xs text-ink-3">{day(i.expires_at)} хүртэл</span>
      <button
        type="button"
        onClick={() => revoke.mutate({ params: { path: { invite_id: i.id } } })}
        className="ml-auto text-xs text-ink-3 underline hover:text-ink"
      >
        Цуцлах
      </button>
    </li>
  )
}
