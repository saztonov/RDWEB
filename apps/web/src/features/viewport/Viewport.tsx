/**
 * Основной viewport — scroll-контейнер для страниц PDF.
 *
 * Отвечает за:
 * - отображение всех PageSlot-ов
 * - wheel zoom (Ctrl+wheel)
 * - центрирование страниц
 */

import { useCallback, useRef } from 'react'
import type { PDFDocumentProxy } from 'pdfjs-dist'

import { useEditorStore } from '../../store/useEditorStore'
import { selectPages, selectZoom } from '../../store/selectors'
import { PageSlot } from './PageSlot'

interface ViewportProps {
  pdfDocument: PDFDocumentProxy
}

export function Viewport({ pdfDocument }: ViewportProps) {
  const pages = useEditorStore(selectPages)
  const zoom = useEditorStore(selectZoom)
  const setZoom = useEditorStore((s) => s.setZoom)
  const containerRef = useRef<HTMLDivElement>(null)

  // Ctrl+wheel = zoom, обычный wheel = scroll
  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault()
        const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15
        setZoom(zoom * factor)
      }
    },
    [zoom, setZoom],
  )

  return (
    <div
      ref={containerRef}
      onWheel={handleWheel}
      style={{
        flex: 1,
        overflow: 'auto',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        padding: '16px 0',
        backgroundColor: '#e8e8e8',
      }}
    >
      {pages.map((page) => (
        <PageSlot
          key={page.pageNumber}
          page={page}
          pdfDocument={pdfDocument}
          zoom={zoom}
        />
      ))}
    </div>
  )
}
