import { Navigate, Route, Routes } from 'react-router'
import { useToken } from './auth/token'
import Layout from './Layout'
import GameplanPage from './pages/GameplanPage'
import GameplanPickPage from './pages/GameplanPickPage'
import HomePage from './pages/HomePage'
import JobPage from './pages/JobPage'
import JobsPage from './pages/JobsPage'
import LoginPage from './pages/LoginPage'
import MatchPage from './pages/MatchPage'
import TeamPage from './pages/TeamPage'
import TeamsPage from './pages/TeamsPage'

export default function App() {
  const token = useToken()
  // Signed out, every URL shows the login form; signing in lands on the same URL.
  if (!token) return <LoginPage />

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="jobs" element={<JobsPage />} />
        <Route path="jobs/:publicId" element={<JobPage />} />
        <Route path="teams" element={<TeamsPage />} />
        <Route path="teams/:teamId" element={<TeamPage />} />
        <Route path="matches/:matchId" element={<MatchPage />} />
        <Route path="matches/:matchId/m/:mapNumber" element={<MatchPage />} />
        <Route path="gameplan" element={<GameplanPickPage />} />
        <Route path="gameplan/:mine/vs/:theirs" element={<GameplanPage />} />
        <Route path="gameplan/:mine/vs/:theirs/s/:tab" element={<GameplanPage />} />
        <Route path="gameplan/:mine/vs/:theirs/s/:tab/m/:map" element={<GameplanPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
