import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider, Spin } from 'antd'
import ruRU from 'antd/locale/ru_RU'
import MainLayout from './layouts/MainLayout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import PromptTemplatesPage from './pages/admin/PromptTemplatesPage'
import PromptTemplateDetailPage from './pages/admin/PromptTemplateDetailPage'

const DocumentEditorPage = lazy(() => import('./features/editor/DocumentEditorPage'))

function App() {
  return (
    <ConfigProvider locale={ruRU}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<MainLayout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<DashboardPage />} />
            <Route path="admin/prompts" element={<PromptTemplatesPage />} />
            <Route path="admin/prompts/:id" element={<PromptTemplateDetailPage />} />
            <Route
              path="documents/:id"
              element={
                <Suspense fallback={<Spin size="large" style={{ display: 'flex', justifyContent: 'center', marginTop: 100 }} />}>
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
