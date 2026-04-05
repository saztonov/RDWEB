/**
 * Hook для конвертации координат screen ↔ page.
 *
 * SVG viewBox совпадает с page dimensions, поэтому для рендеринга блоков
 * конвертация не нужна. Этот hook нужен только для обработки mouse events:
 * clientX/clientY → page coords.
 */

import { useCallback } from 'react'

interface CoordinateTransformOptions {
  /** SVG/canvas элемент, относительно которого считаем координаты */
  containerRef: React.RefObject<HTMLElement | SVGSVGElement | null>
  /** Размеры страницы PDF (px) */
  pageWidth: number
  pageHeight: number
  /** Текущий zoom (для использования в будущем) */
  zoom?: number
}

interface CoordinateTransform {
  /** Из screen (clientX, clientY) в page coords */
  screenToPage: (clientX: number, clientY: number) => { x: number; y: number }
  /** Из page coords в screen (для hit testing с фиксированными px зонами) */
  pageToScreen: (pageX: number, pageY: number) => { x: number; y: number }
  /** Расстояние в screen px → расстояние в page coords */
  screenToPageDistance: (screenPx: number) => number
}

export function useCoordinateTransform({
  containerRef,
  pageWidth,
  pageHeight,
  zoom: _zoom,
}: CoordinateTransformOptions): CoordinateTransform {
  const screenToPage = useCallback(
    (clientX: number, clientY: number) => {
      const el = containerRef.current
      if (!el) return { x: 0, y: 0 }

      const rect = el.getBoundingClientRect()
      // Позиция внутри элемента в screen px
      const screenX = clientX - rect.left
      const screenY = clientY - rect.top

      // Элемент отображается с размером pageWidth*zoom × pageHeight*zoom
      // Page coords = screen coords / zoom
      const displayWidth = rect.width
      const displayHeight = rect.height

      const x = (screenX / displayWidth) * pageWidth
      const y = (screenY / displayHeight) * pageHeight

      return { x, y }
    },
    [containerRef, pageWidth, pageHeight],
  )

  const pageToScreen = useCallback(
    (pageX: number, pageY: number) => {
      const el = containerRef.current
      if (!el) return { x: 0, y: 0 }

      const rect = el.getBoundingClientRect()
      const x = rect.left + (pageX / pageWidth) * rect.width
      const y = rect.top + (pageY / pageHeight) * rect.height

      return { x, y }
    },
    [containerRef, pageWidth, pageHeight],
  )

  const screenToPageDistance = useCallback(
    (screenPx: number) => {
      const el = containerRef.current
      if (!el) return screenPx

      const rect = el.getBoundingClientRect()
      // Масштаб: сколько page px в одном screen px
      return (screenPx / rect.width) * pageWidth
    },
    [containerRef, pageWidth],
  )

  return { screenToPage, pageToScreen, screenToPageDistance }
}
