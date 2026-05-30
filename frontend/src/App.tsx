import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Workbench from './pages/Workbench'
import Ask from './pages/Ask'
import Patents from './pages/Patents'
import Signals from './pages/Signals'
import Evidence from './pages/Evidence'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/workbench" element={<Workbench />} />
        <Route path="/ask" element={<Ask />} />
        <Route path="/patents" element={<Patents />} />
        <Route path="/signals" element={<Signals />} />
        <Route path="/evidence" element={<Evidence />} />
      </Routes>
    </Layout>
  )
}
