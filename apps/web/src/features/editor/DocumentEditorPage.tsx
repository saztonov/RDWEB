/**
 * Страница редактора документа — route /documents/:id
 *
 * Загружает документ, инициализирует PDF.js, рендерит EditorLayout.
 */

import { useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { Result, Spin } from 'antd'

import { usePdfDocument } from '../../hooks/usePdfDocument'
import { useBlockRealtimeUpdates } from '../../hooks/useBlockRealtimeUpdates'
import { useEditorStore } from '../../store/useEditorStore'
import { EditorLayout } from './EditorLayout'

export default function DocumentEditorPage() {
  const { id } = useParams<{ id: string }>()
  const loadDocument = useEditorStore((s) => s.loadDocument)
  const pdfUrl = useEditorStore((s) => s.pdfUrl)
  const documentLoading = useEditorStore((s) => s.documentLoading)
  const documentError = useEditorStore((s) => s.documentError)
  const documentTitle = useEditorStore((s) => s.documentTitle)

  // Загрузить метаданные документа
  useEffect(() => {
    if (id) {
      loadDocument(id)
    }
  }, [id, loadDocument])

  // Supabase Realtime: live обновления блоков и recognition progress
  useBlockRealtimeUpdates(id ?? null)

  // TODO: pdfUrl будет устанавливаться из R2 signed URL после реализации upload
  // Пока для тестирования можно задать вручную через store.setPdfUrl()
  const { pdfDocument, loading: pdfLoading, error: pdfError } = usePdfDocument(pdfUrl)

  if (documentLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
        <Spin size="large" tip="Загрузка документа..." />
      </div>
    )
  }

  if (documentError) {
    return <Result status="error" title="Ошибка загрузки" subTitle={documentError} />
  }

  if (!pdfUrl) {
    return (
      <Result
        status="info"
        title={documentTitle || 'Документ'}
        subTitle="PDF файл не загружен. Ожидается URL документа."
      />
    )
  }

  if (pdfLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
        <Spin size="large" tip="Загрузка PDF..." />
      </div>
    )
  }

  if (pdfError) {
    return <Result status="error" title="Ошибка PDF" subTitle={pdfError} />
  }

  if (!pdfDocument) {
    return null
  }

  return <EditorLayout pdfDocument={pdfDocument} />
}
