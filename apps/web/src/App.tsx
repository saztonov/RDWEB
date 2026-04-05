import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider, Spin } from 'antd'
import ruRU from 'antd/locale/ru_RU'
import MainLayout from './layouts/MainLayout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import PromptTemplatesPage from './pages/admin/PromptTemplatesPage'
import PromptTemplateDetailPage from './pages/admin/PromptTemplateDetailPage'
import AdminOverviewPage from './pages/admin/AdminOverviewPage'
import AdminSourcesPage from './pages/admin/AdminSourcesPage'
import AdminRunsPage from './pages/admin/AdminRunsPage'
import AdminRunDetailPage from './pages/admin/AdminRunDetailPage'
import AdminIncidentsPage from './pages/admin/AdminIncidentsPage'
import AdminEventsPage from './pages/admin/AdminEventsPage'

const DocumentEditorPage = lazy(() => import('./features/editor/DocumentEditorPage'))

const editorFallback = <Spin size="large" style={{ display: 'flex', justifyContent: 'center', marginTop: 100 }} />

function App() {
  return (
    <ConfigProvider locale={ruRU}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<MainLayout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<DashboardPage />} />
            {/* Admin / Ops */}
            <Route path="admin/overview" element={<AdminOverviewPage />} />
            <Route path="admin/sources" element={<AdminSourcesPage />} />
            <Route path="admin/runs" element={<AdminRunsPage />} />
            <Route path="admin/runs/:id" element={<AdminRunDetailPage />} />
            <Route path="admin/incidents" element={<AdminIncidentsPage />} />
            <Route path="admin/logs" element={<AdminEventsPage />} />
            <Route path="admin/prompts" element={<PromptTemplatesPage />} />
            <Route path="admin/prompts/:id" element={<PromptTemplateDetailPage />} />
            {/* Document Editor */}
            <Route
              path="documents/:id"
              element={
                <Suspense fallback={editorFallback}>
                  <DocumentEditorPage />
                </Suspense>
              }
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}

export default App
