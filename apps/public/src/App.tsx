import { lazy } from 'react'
import { Navigate, Route, Routes, useMatch } from 'react-router'
import { useToken } from './auth/token'
import { useMe } from './auth/useMe'
import Layout from './Layout'
import HomePage from './pages/HomePage'
import InvitePage from './pages/InvitePage'
import JobPage from './pages/JobPage'
import JobsPage from './pages/JobsPage'
import LoginPage from './pages/LoginPage'
import MePage from './pages/MePage'
import TeamsPage from './pages/TeamsPage'
import V2Layout from './v2/V2Layout'


// OPS-8: the heavy pages (the Replay, the Game Plan, the Stratbook...) load when
// first opened; Layout shows a skeleton meanwhile.
const AgendaPage = lazy(() => import('./pages/AgendaPage'))
const BriefingNewPage = lazy(() => import('./pages/BriefingNewPage'))
const BriefingPage = lazy(() => import('./pages/BriefingPage'))
const BriefingsPage = lazy(() => import('./pages/BriefingsPage'))
const ForecastsPage = lazy(() => import('./pages/ForecastsPage'))
const GameplanPage = lazy(() => import('./pages/GameplanPage'))
const GameplanPickPage = lazy(() => import('./pages/GameplanPickPage'))
const MatchPage = lazy(() => import('./pages/MatchPage'))
const GhostPage = lazy(() => import('./pages/GhostPage'))
const LineupsPage = lazy(() => import('./pages/LineupsPage'))
const MapSheetPage = lazy(() => import('./pages/MapSheetPage'))
const PlayerPage = lazy(() => import('./pages/PlayerPage'))
const PlaylistPage = lazy(() => import('./pages/PlaylistsPage').then((m) => ({ default: m.PlaylistPage })))
const PlaylistsPage = lazy(() => import('./pages/PlaylistsPage').then((m) => ({ default: m.PlaylistsPage })))
const ScrimsPage = lazy(() => import('./pages/ScrimsPage'))
const SearchPage = lazy(() => import('./pages/SearchPage'))
const DataPage = lazy(() => import('./pages/DataPage'))
const WeekPage = lazy(() => import('./pages/WeekPage'))
const ComparePage = lazy(() => import('./pages/ComparePage'))
const StratbookPage = lazy(() => import('./pages/StratbookPage').then((m) => ({ default: m.StratbookPage })))
const StratNewPage = lazy(() => import('./pages/StratbookPage').then((m) => ({ default: m.StratNewPage })))
const StratPage = lazy(() => import('./pages/StratbookPage').then((m) => ({ default: m.StratPage })))
const TeamPage = lazy(() => import('./pages/TeamPage'))
const UploadsPage = lazy(() => import('./pages/UploadsPage'))
const VetoLabPage = lazy(() => import('./pages/VetoLabPage'))
const WorkspacePage = lazy(() => import('./pages/WorkspacePage'))
// v2 (the DEMOLAB design, docs/adr/0013): /v2/t/:team/..., in its own frame.
const V2Overview = lazy(() => import('./v2/pages/OverviewPage'))
const V2Matches = lazy(() => import('./v2/pages/MatchesPage'))
const V2MatchReport = lazy(() => import('./v2/pages/MatchReportPage'))

export default function App() {
  const token = useToken()
  // An invite link opens before anyone signs in (docs/plans WS-3).
  const invite = useMatch('/invite/:token')
  if (invite?.params.token) return <InvitePage token={invite.params.token} />
  // Signed out, every URL shows the login form; signing in lands on the same URL.
  if (!token) return <LoginPage />

  return (
    <Routes>
      <Route path="v2" element={<V2Layout />} />
      <Route path="v2/t/:team" element={<V2Layout />}>
        <Route index element={<V2Overview />} />
        <Route path="matches" element={<V2Matches />} />
        <Route path="matches/:matchId/m/:mapNumber" element={<V2MatchReport />} />
      </Route>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="me" element={<MePage />} />
        <Route path="jobs" element={<JobsPage />} />
        <Route path="jobs/:publicId" element={<JobPage />} />
        <Route path="teams" element={<TeamsPage />} />
        <Route path="teams/:teamId" element={<TeamPage />} />
        <Route path="matches/:matchId" element={<MatchPage />} />
        <Route path="matches/:matchId/m/:mapNumber" element={<MatchPage />} />
        <Route path="matches/:matchId/agenda" element={<AgendaPage />} />
        <Route path="players/:steamid" element={<PlayerPage />} />
        <Route path="gameplan" element={<GameplanPickPage />} />
        <Route path="forecasts" element={<ForecastsPage />} />
        <Route path="briefings" element={<BriefingsPage />} />
        <Route path="briefings/:id" element={<BriefingPage />} />
        <Route path="gameplan/:mine/vs/:theirs/briefing" element={<BriefingNewPage />} />
        <Route path="gameplan/:mine/vs/:theirs/sheet/:map" element={<MapSheetPage />} />
        <Route path="gameplan/:mine/vs/:theirs/veto" element={<VetoLabPage />} />
        <Route path="uploads" element={<UploadsPage />} />
        <Route path="scrims" element={<ScrimsPage />} />
        <Route path="playlists" element={<PlaylistsPage />} />
        <Route path="stratbook" element={<StratbookPage />} />
        <Route path="lineups" element={<LineupsPage />} />
        <Route path="ghost" element={<GhostPage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="data" element={<DataPage />} />
        <Route path="week" element={<WeekPage />} />
        <Route path="compare" element={<ComparePage />} />
        <Route path="stratbook/new" element={<StratNewPage />} />
        <Route path="stratbook/:stratId" element={<StratPage />} />
        <Route path="playlists/:playlistId" element={<PlaylistPage />} />
        <Route path="workspace" element={<WorkspacePage />} />
        <Route path="gameplan/:mine/vs/:theirs" element={<GameplanPage />} />
        <Route path="gameplan/:mine/vs/:theirs/s/:tab" element={<GameplanPage />} />
        <Route path="gameplan/:mine/vs/:theirs/s/:tab/m/:map" element={<GameplanPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

// Staff land on the Scout form; a Player login on its own page (docs/plans WS-4).
function Home() {
  const me = useMe()
  if (!me.data) return null
  return me.data.role === 'player' ? <Navigate to="/me" replace /> : <HomePage />
}
