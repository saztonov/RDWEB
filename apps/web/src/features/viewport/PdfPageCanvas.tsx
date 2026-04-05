/**
 * Рендеринг одной страницы PDF в <canvas>.
 *
 * КРИТИЧНО: React.memo — overlay-изменения НЕ должны перерендеривать canvas.
 * Props: pageNumber, pdfDocument, zoom — только они вызывают ре-рендер.
 */

import { memo, useEffect, useRef } from 'react'
import type { PDFDocumentProxy } from 'pdfjs-dist'

interface PdfPageCanvasProps {
  pageNumber: number
  pdfDocument: PDFDocumentProxy
  zoom: number
  width: number
  height: number
}

export const PdfPageCanvas = memo(function PdfPageCanvas({
  pageNumber,
  pdfDocument,
  zoom,
  width,
  height,
}: PdfPageCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const renderTaskRef = useRef<ReturnType<
    Awaited<ReturnType<PDFDocumentProxy['getPage']>>['render']
  > | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !pdfDocument) return

    let cancelled = false

    const renderPage = async () => {
      // Отменить предыдущий рендер
      if (renderTaskRef.current) {
        renderTaskRef.current.cancel()
        renderTaskRef.current = null
      }

      try {
        const page = await pdfDocument.getPage(pageNumber)
        if (cancelled) return

        // devicePixelRatio для чёткости на HiDPI
        const dpr = window.devicePixelRatio || 1
        const viewport = page.getViewport({ scale: zoom * dpr })

        canvas.width = viewport.width
        canvas.height = viewport.height
        canvas.style.width = `${width * zoom}px`
        canvas.style.height = `${height * zoom}px`

        const ctx = canvas.getContext('2d')
        if (!ctx) return

        const renderTask = page.render({
          canvasContext: ctx,
          viewport,
          canvas,
        })
        renderTaskRef.current = renderTask

        await renderTask.promise
      } catch (err: unknown) {
        // RenderingCancelledException — нормальная ситуация при быстром переключении
        if (err && typeof err === 'object' && 'name' in err && err.name === 'RenderingCancelledException') return
        if (!cancelled) {
          console.error('Ошибка рендеринга страницы PDF:', err)
        }
      }
    }

    renderPage()

    return () => {
      cancelled = true
      if (renderTaskRef.current) {
        renderTaskRef.current.cancel()
        renderTaskRef.current = null
      }
    }
  }, [pageNumber, pdfDocument, zoom, width, height])

  return (
    <canvas
      ref={canvasRef}
      style={{
        display: 'block',
        width: width * zoom,
        height: height * zoom,
      }}
    />
  )
})
