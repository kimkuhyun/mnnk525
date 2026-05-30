import { Routes, Route, Navigate } from 'react-router-dom'
import Landing from './pages/Landing'
import Workspace from './pages/Workspace'

export default function App() {
  return (
    <Routes>
      {/* 진입화면 — 풀스크린 (기존 유지) */}
      <Route path="/" element={<Landing />} />
      {/* 인텔리전스 워크스페이스 — 트렌드 띠 + 관계지도 한 화면 */}
      <Route path="/app" element={<Workspace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
