/**
 * Hook для обработки взаимодействия с блоками на SVG overlay.
 *
 * State machine адаптирована из legacy page_viewer_mouse.py:
 * - Left click: рисование / выделение / перемещение / resize
 * - Right drag: rubber-band выделение
 * - Middle drag: pan (нативный scroll)
 * - Ctrl+click: multi-select
 *
 * Использует pointer events для совместимости с touch.
 * Читает state через getState() чтобы избежать ре-рендеров.
 */

import { useCallback, useRef } from 'react'
import { useCoordinateTransform } from './useCoordinateTransform'
import { useEditorStore } from '../store/useEditorStore'
import type { BlockCoords } from '../types/block'
import { MIN_BLOCK_SIZE, MIN_POLYGON_VERTICES, ShapeType } from '../types/block'
import type { PagePoint, ResizeHandle } from '../types/editor'
import { InteractionState } from '../types/editor'

interface UseBlockInteractionOptions {
  svgRef: React.RefObject<SVGSVGElement | null>
  pageNumber: number
  pageWidth: number
  pageHeight: number
}

/** Clamp точку к границам страницы */
function clampToPage(point: PagePoint, w: number, h: number): PagePoint {
  return {
    x: Math.max(0, Math.min(w, point.x)),
    y: Math.max(0, Math.min(h, point.y)),
  }
}

/** Нормализовать bbox (width/height всегда > 0) */
function normalizeBbox(x1: number, y1: number, x2: number, y2: number): BlockCoords {
  return {
    x: Math.min(x1, x2),
    y: Math.min(y1, y2),
    width: Math.abs(x2 - x1),
    height: Math.abs(y2 - y1),
  }
}

/** Применить resize handle к bbox */
function applyResize(
  original: BlockCoords,
  handle: ResizeHandle,
  dx: number,
  dy: number,
  pageW: number,
  pageH: number,
): BlockCoords {
  let { x, y, width, height } = original
  const x2 = x + width
  const y2 = y + height

  let nx1 = x, ny1 = y, nx2 = x2, ny2 = y2

  switch (handle) {
    case 'tl': nx1 += dx; ny1 += dy; break
    case 'tr': nx2 += dx; ny1 += dy; break
    case 'bl': nx1 += dx; ny2 += dy; break
    case 'br': nx2 += dx; ny2 += dy; break
    case 't': ny1 += dy; break
    case 'b': ny2 += dy; break
    case 'l': nx1 += dx; break
    case 'r': nx2 += dx; break
  }

  // Clamp к странице
  nx1 = Math.max(0, Math.min(pageW, nx1))
  ny1 = Math.max(0, Math.min(pageH, ny1))
  nx2 = Math.max(0, Math.min(pageW, nx2))
  ny2 = Math.max(0, Math.min(pageH, ny2))

  // Минимальный размер
  const result = normalizeBbox(nx1, ny1, nx2, ny2)
  if (result.width < MIN_BLOCK_SIZE) result.width = MIN_BLOCK_SIZE
  if (result.height < MIN_BLOCK_SIZE) result.height = MIN_BLOCK_SIZE

  return result
}

/** Bounding box из polygon points */
function bboxFromPolygon(points: [number, number][]): BlockCoords {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const [px, py] of points) {
    if (px < minX) minX = px
    if (py < minY) minY = py
    if (px > maxX) maxX = px
    if (py > maxY) maxY = py
  }
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY }
}

export function useBlockInteraction({
  svgRef,
  pageNumber,
  pageWidth,
  pageHeight,
}: UseBlockInteractionOptions) {
  const zoom = useEditorStore((s) => s.zoom)

  const { screenToPage } = useCoordinateTransform({
    containerRef: svgRef,
    pageWidth,
    pageHeight,
    zoom,
  })

  // Ref для отслеживания перемещения (чтобы отличить click от drag)
  const hasMoved = useRef(false)

  /** Найти block ID из SVG event target */
  const findBlockIdFromTarget = useCallback((target: EventTarget | null): string | null => {
    let el = target as SVGElement | null
    while (el && el !== svgRef.current) {
      const blockId = el.getAttribute?.('data-block-id')
      if (blockId) return blockId
      el = el.parentElement as SVGElement | null
    }
    return null
  }, [svgRef])

  // ────────────────────────────────────────
  // Pointer Down
  // ────────────────────────────────────────

  const handlePointerDown = useCallback(
    (e: React.PointerEvent<SVGSVGElement>) => {
      const store = useEditorStore.getState()
      const point = clampToPage(screenToPage(e.clientX, e.clientY), pageWidth, pageHeight)

      // Middle button — нативный scroll (не перехватываем)
      if (e.button === 1) return

      // Right button — rubber-band selection
      if (e.button === 2) {
        e.preventDefault()
        store.transitionTo(InteractionState.SELECTING)
        store.setDrawingOrigin(point)
        store.setDrawingCurrent(point)
        ;(e.target as Element).setPointerCapture?.(e.pointerId)
        hasMoved.current = false
        return
      }

      // Left button
      if (e.button !== 0) return

      const { interactionState, activeShapeType, selectedIds, blocksByPage } = store

      // Если рисуем polygon — добавить точку
      if (interactionState === InteractionState.DRAWING_POLYGON) {
        store.addDrawingPoint(point)
        return
      }

      // Найти блок под курсором
      const blockId = findBlockIdFromTarget(e.target)

      // Ctrl+click — toggle multi-select
      if (blockId && (e.ctrlKey || e.metaKey)) {
        store.toggleSelect(blockId)
        return
      }

      // Клик на уже выделенный блок → начать перемещение
      if (blockId && selectedIds.has(blockId)) {
        const blocks = blocksByPage[pageNumber] ?? []
        const block = blocks.find((b) => b.id === blockId)
        if (block) {
          store.transitionTo(InteractionState.MOVING_BLOCK)
          store.setDragOrigin(point)
          store.setOriginalBbox(block.bboxJson)
          if (block.polygonJson) {
            store.setOriginalPolygonPoints(block.polygonJson)
          }
          ;(e.target as Element).setPointerCapture?.(e.pointerId)
          hasMoved.current = false
        }
        return
      }

      // Клик на невыделенный блок → выделить
      if (blockId) {
        store.selectBlock(blockId)
        return
      }

      // Клик на пустое место → начать рисование
      if (activeShapeType === ShapeType.POLYGON) {
        store.transitionTo(InteractionState.DRAWING_POLYGON)
        store.setDrawingPoints([point])
        store.setDrawingCurrent(point)
      } else {
        store.transitionTo(InteractionState.DRAWING_RECT)
        store.setDrawingOrigin(point)
        store.setDrawingCurrent(point)
        ;(e.target as Element).setPointerCapture?.(e.pointerId)
        hasMoved.current = false
      }
    },
    [screenToPage, pageWidth, pageHeight, pageNumber, findBlockIdFromTarget],
  )

  // ────────────────────────────────────────
  // Pointer Move
  // ────────────────────────────────────────

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<SVGSVGElement>) => {
      const store = useEditorStore.getState()
      const { interactionState } = store
      if (interactionState === InteractionState.IDLE) return

      const point = clampToPage(screenToPage(e.clientX, e.clientY), pageWidth, pageHeight)
      hasMoved.current = true

      switch (interactionState) {
        case InteractionState.DRAWING_RECT:
        case InteractionState.SELECTING:
          store.setDrawingCurrent(point)
          break

        case InteractionState.DRAWING_POLYGON:
          store.setDrawingCurrent(point)
          break

        case InteractionState.MOVING_BLOCK: {
          const { dragOrigin, originalBbox, originalPolygonPoints, selectedIds, blocksByPage } = store
          if (!dragOrigin || !originalBbox) break
          const dx = point.x - dragOrigin.x
          const dy = point.y - dragOrigin.y

          // Переместить все выделенные блоки
          for (const blockId of selectedIds) {
            const blocks = blocksByPage[pageNumber] ?? []
            const block = blocks.find((b) => b.id === blockId)
            if (!block) continue

            // Для первого (основного) блока используем originalBbox
            const isMainBlock = block.bboxJson === originalBbox || (
              block.bboxJson.x === originalBbox.x &&
              block.bboxJson.y === originalBbox.y
            )

            if (isMainBlock) {
              const newBbox: BlockCoords = {
                x: Math.max(0, Math.min(pageWidth - originalBbox.width, originalBbox.x + dx)),
                y: Math.max(0, Math.min(pageHeight - originalBbox.height, originalBbox.y + dy)),
                width: originalBbox.width,
                height: originalBbox.height,
              }

              let newPolygon: [number, number][] | null = null
              if (originalPolygonPoints) {
                newPolygon = originalPolygonPoints.map(([px, py]) => [
                  Math.max(0, Math.min(pageWidth, px + dx)),
                  Math.max(0, Math.min(pageHeight, py + dy)),
                ] as [number, number])
              }

              store.updateBlockGeometry(blockId, newBbox, newPolygon)
            }
          }
          break
        }

        case InteractionState.RESIZING_BLOCK: {
          const { dragOrigin, originalBbox, resizeHandle, selectedIds } = store
          if (!dragOrigin || !originalBbox || !resizeHandle) break
          const dx = point.x - dragOrigin.x
          const dy = point.y - dragOrigin.y

          const newBbox = applyResize(originalBbox, resizeHandle, dx, dy, pageWidth, pageHeight)
          const blockId = selectedIds.values().next().value
          if (blockId) {
            store.updateBlockGeometry(blockId, newBbox)
          }
          break
        }

        case InteractionState.DRAGGING_POLYGON_VERTEX: {
          const { dragVertexIdx, selectedIds, blocksByPage } = store
          if (dragVertexIdx === null) break
          const blockId = selectedIds.values().next().value
          if (!blockId) break
          const blocks = blocksByPage[pageNumber] ?? []
          const block = blocks.find((b) => b.id === blockId)
          if (!block?.polygonJson) break

          const newPoints: [number, number][] = block.polygonJson.map((pt, i) =>
            i === dragVertexIdx ? [point.x, point.y] : pt,
          )
          const newBbox = bboxFromPolygon(newPoints)
          store.updateBlockGeometry(blockId, newBbox, newPoints)
          break
        }

        case InteractionState.DRAGGING_POLYGON_EDGE: {
          const { dragEdgeIdx, dragOrigin, originalPolygonPoints, selectedIds } = store
          if (dragEdgeIdx === null || !dragOrigin || !originalPolygonPoints) break
          const dx = point.x - dragOrigin.x
          const dy = point.y - dragOrigin.y

          const blockId = selectedIds.values().next().value
          if (!blockId) break

          const i1 = dragEdgeIdx
          const i2 = (dragEdgeIdx + 1) % originalPolygonPoints.length

          const newPoints: [number, number][] = originalPolygonPoints.map((pt, i) => {
            if (i === i1 || i === i2) {
              return [
                Math.max(0, Math.min(pageWidth, pt[0] + dx)),
                Math.max(0, Math.min(pageHeight, pt[1] + dy)),
              ] as [number, number]
            }
            return pt
          })
          const newBbox = bboxFromPolygon(newPoints)
          store.updateBlockGeometry(blockId, newBbox, newPoints)
          break
        }
      }
    },
    [screenToPage, pageWidth, pageHeight, pageNumber],
  )

  // ────────────────────────────────────────
  // Pointer Up
  // ────────────────────────────────────────

  const handlePointerUp = useCallback(
    (_e: React.PointerEvent<SVGSVGElement>) => {
      const store = useEditorStore.getState()
      const { interactionState } = store

      switch (interactionState) {
        case InteractionState.DRAWING_RECT: {
          const { drawingOrigin, drawingCurrent, activeBlockKind } = store
          if (drawingOrigin && drawingCurrent) {
            const bbox = normalizeBbox(
              drawingOrigin.x,
              drawingOrigin.y,
              drawingCurrent.x,
              drawingCurrent.y,
            )
            // Минимальный размер (из legacy: 10×10)
            if (bbox.width >= MIN_BLOCK_SIZE && bbox.height >= MIN_BLOCK_SIZE) {
              store.addBlock({
                blockKind: activeBlockKind,
                shapeType: ShapeType.RECTANGLE,
                pageNumber,
                bboxJson: bbox,
              })
            }
          }
          store.resetInteraction()
          break
        }

        case InteractionState.SELECTING: {
          const { drawingOrigin, drawingCurrent } = store
          if (drawingOrigin && drawingCurrent) {
            const rect = normalizeBbox(
              drawingOrigin.x,
              drawingOrigin.y,
              drawingCurrent.x,
              drawingCurrent.y,
            )
            // Минимальный размер rubber band (из legacy: 5×5)
            if (rect.width >= 5 && rect.height >= 5) {
              store.selectInRect(pageNumber, rect)
            }
          }
          store.resetInteraction()
          break
        }

        case InteractionState.MOVING_BLOCK:
        case InteractionState.RESIZING_BLOCK:
        case InteractionState.DRAGGING_POLYGON_VERTEX:
        case InteractionState.DRAGGING_POLYGON_EDGE:
          store.resetInteraction()
          break
      }
    },
    [pageNumber],
  )

  // ────────────────────────────────────────
  // Double Click — завершить polygon
  // ────────────────────────────────────────

  const handleDoubleClick = useCallback(
    (_e: React.MouseEvent<SVGSVGElement>) => {
      const store = useEditorStore.getState()
      if (store.interactionState !== InteractionState.DRAWING_POLYGON) return

      const { drawingPoints, activeBlockKind } = store

      // Минимум 3 вершины (из legacy validation_mixin.py)
      if (drawingPoints.length >= MIN_POLYGON_VERTICES) {
        const polygon: [number, number][] = drawingPoints.map((p) => [p.x, p.y])
        const bbox = bboxFromPolygon(polygon)

        store.addBlock({
          blockKind: activeBlockKind,
          shapeType: ShapeType.POLYGON,
          pageNumber,
          bboxJson: bbox,
          polygonJson: polygon,
        })
      }

      store.resetInteraction()
    },
    [pageNumber],
  )

  // ────────────────────────────────────────
  // Context menu (prevent default для right-click selection)
  // ────────────────────────────────────────

  const handleContextMenu = useCallback((evt: React.MouseEvent) => {
    evt.preventDefault()
  }, [])

  // ────────────────────────────────────────
  // Resize handle start
  // ────────────────────────────────────────

  const handleResizeStart = useCallback(
    (handle: ResizeHandle, e: React.PointerEvent) => {
      const store = useEditorStore.getState()
      const blockId = store.selectedIds.values().next().value
      if (!blockId) return

      const blocks = store.blocksByPage[pageNumber] ?? []
      const block = blocks.find((b) => b.id === blockId)
      if (!block) return

      const point = screenToPage(e.clientX, e.clientY)
      store.transitionTo(InteractionState.RESIZING_BLOCK)
      store.setResizeHandle(handle)
      store.setDragOrigin(point)
      store.setOriginalBbox(block.bboxJson)
    },
    [pageNumber, screenToPage],
  )

  // ────────────────────────────────────────
  // Polygon vertex/edge start
  // ────────────────────────────────────────

  const handleVertexStart = useCallback(
    (vertexIdx: number, e: React.PointerEvent) => {
      const store = useEditorStore.getState()
      store.transitionTo(InteractionState.DRAGGING_POLYGON_VERTEX)
      store.setDragVertexIdx(vertexIdx)
      const point = screenToPage(e.clientX, e.clientY)
      store.setDragOrigin(point)
    },
    [screenToPage],
  )

  const handleEdgeStart = useCallback(
    (edgeIdx: number, e: React.PointerEvent) => {
      const store = useEditorStore.getState()
      const blockId = store.selectedIds.values().next().value
      if (!blockId) return
      const blocks = store.blocksByPage[pageNumber] ?? []
      const block = blocks.find((b) => b.id === blockId)
      if (!block?.polygonJson) return

      store.transitionTo(InteractionState.DRAGGING_POLYGON_EDGE)
      store.setDragEdgeIdx(edgeIdx)
      const point = screenToPage(e.clientX, e.clientY)
      store.setDragOrigin(point)
      store.setOriginalPolygonPoints(block.polygonJson)
    },
    [pageNumber, screenToPage],
  )

  return {
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handleDoubleClick,
    handleContextMenu,
    handleResizeStart,
    handleVertexStart,
    handleEdgeStart,
  }
}
