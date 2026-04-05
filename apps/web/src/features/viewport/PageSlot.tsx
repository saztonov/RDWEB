/**
 * Slot для одной страницы PDF.
 *
 * IntersectionObserver виртуализация: рендерит PdfPageCanvas + OverlaySvg
 * только когда slot видим в viewport (+ 200px margin для предзагрузки).
 * Невидимые страницы — пустой div с фиксированной высотой.
 */

import { useEffect, useRef, useState } from 'react'
import type { PDFDocumentProxy } from 'pdfjs-dist'

import { useEditorStore } from '../../store/useEditorStore'
import type { PageMeta } from '../../types/editor'
import { OverlaySvg } from './OverlaySvg'
import { PdfPageCanvas } from './PdfPageCanvas'

interface PageSlotProps {
  page: PageMeta
  pdfDocument: PDFDocumentProxy
  zoom: number
}

export function PageSlot({ page, pdfDocument, zoom }: PageSlotProps) {
  const [isVisible, setIsVisible] = useState(false)
  const slotRef = useRef<HTMLDivElement>(null)
  const loadBlocksForPage = useEditorStore((s) => s.loadBlocksForPage)

  // IntersectionObserver — отслеживаем видимость
  useEffect(() => {
    const el = slotRef.current
    if (!el) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        setIsVisible(entry.isIntersecting)
      },
      {
        // Предзагрузка: 200px выше и ниже viewport
        rootMargin: '200px 0px',
        threshold: 0,
      },
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  // Загрузить блоки при появлении страницы
  useEffect(() => {
    if (isVisible) {
      loadBlocksForPage(page.pageNumber)
    }
  }, [isVisible, page.pageNumber, loadBlocksForPage])

  const displayWidth = page.width * zoom
  const displayHeight = page.height * zoom

  return (
    <div
      ref={slotRef}
      style={{
        width: displayWidth,
        height: displayHeight,
        position: 'relative',
        marginBottom: 8,
        backgroundColor: '#f0f0f0',
        boxShadow: '0 1px 4px rgba(0,0,0,0.15)',
      }}
      data-page-number={page.pageNumber}
    >
      {isVisible && (
        <>
          <PdfPageCanvas
            pageNumber={page.pageNumber}
            pdfDocument={pdfDocument}
            zoom={zoom}
            width={page.width}
            height={page.height}
          />
          <OverlaySvg
            pageNumber={page.pageNumber}
            pageWidth={page.width}
            pageHeight={page.height}
            zoom={zoom}
          />
        </>
      )}
    </div>
  )
}
