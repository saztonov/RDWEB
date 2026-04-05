/**
 * Hook для загрузки PDF документа через PDF.js.
 * Возвращает PDFDocumentProxy для рендеринга отдельных страниц.
 */

import { useEffect, useRef, useState } from 'react'
import * as pdfjsLib from 'pdfjs-dist'

// Настройка worker для PDF.js (Vite-совместимый путь)
pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

type PDFDocumentProxy = Awaited<ReturnType<typeof pdfjsLib.getDocument>['promise']>

interface UsePdfDocumentResult {
  pdfDocument: PDFDocumentProxy | null
  loading: boolean
  error: string | null
  pageCount: number
}

/**
 * Загружает PDF по URL и возвращает PDF.js document proxy.
 * Document proxy стабилен — не меняется при ререндерах.
 */
export function usePdfDocument(url: string | null): UsePdfDocumentResult {
  const [pdfDocument, setPdfDocument] = useState<PDFDocumentProxy | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const loadingTaskRef = useRef<ReturnType<typeof pdfjsLib.getDocument> | null>(null)

  useEffect(() => {
    if (!url) {
      setPdfDocument(null)
      return
    }

    setLoading(true)
    setError(null)

    // Отменить предыдущую загрузку
    if (loadingTaskRef.current) {
      loadingTaskRef.current.destroy()
    }

    const loadingTask = pdfjsLib.getDocument({
      url,
      // Отключить авторендеринг шрифтов — рендерим только в canvas
      disableFontFace: false,
      // Включить cmap для корректной работы с кириллицей
      cMapUrl: 'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.8.69/cmaps/',
      cMapPacked: true,
    })
    loadingTaskRef.current = loadingTask

    loadingTask.promise
      .then((doc) => {
        setPdfDocument(doc)
        setLoading(false)
      })
      .catch((err) => {
        if (err.name !== 'RenderingCancelledException') {
          setError(err.message ?? 'Ошибка загрузки PDF')
          setLoading(false)
        }
      })

    return () => {
      loadingTask.destroy()
    }
  }, [url])

  return {
    pdfDocument,
    loading,
    error,
    pageCount: pdfDocument?.numPages ?? 0,
  }
}
