import { Navigate, Route, Routes, useMatch } from 'react-router'
import { useToken } from './auth/token'
import { useMe } from './auth/useMe'
import Layout from './Layout'
import AgendaPage from './pages/AgendaPage'
import BriefingNewPage from './pages/BriefingNewPage'
import BriefingPage from './pages/BriefingPage'
import BriefingsPage from './pages/BriefingsPage'
import ForecastsPage from './pages/ForecastsPage'
import GameplanPage from './pages/GameplanPage'
import GameplanPickPage from './pages/GameplanPickPage'
import HomePage from './pages/HomePage'
import InvitePage from './pages/InvitePage'
import JobPage from './pages/JobPage'
import JobsPage from './pages/JobsPage'
import LoginPage from './pages/LoginPage'
import MatchPage from './pages/MatchPage'
import MapSheetPage from './pages/MapSheetPage'
import MePage from './pages/MePage'
import PlayerPage from './pages/PlayerPage'
import { PlaylistPage, PlaylistsPage } from './pages/PlaylistsPage'
import ScrimsPage from './pages/ScrimsPage'
import { StratbookPage, StratNewPage, StratPage } from './pages/StratbookPage'
import TeamPage from './pages/TeamPage'
import TeamsPage from './pages/TeamsPage'
import UploadsPage from './pages/UploadsPage'
import VetoLabPage from './pages/VetoLabPage'
import WorkspacePage from './pages/WorkspacePage'

export default function App() {
  const token = useToken()
  // An invite link opens before anyone signs in (docs/plans WS-3).
  const invite = useMatch('/invite/:token')
  if (invite?.params.token) return <InvitePage token={invite.params.token} />
  // Signed out, every URL shows the login form; signing in lands on the same URL.
  if (!token) return <LoginPage />

  return (
    <Routes>
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
