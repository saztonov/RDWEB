/**
 * SVG overlay слой поверх PDF canvas.
 *
 * Рендерит блоки страницы, handles, selection rect, drawing preview.
 * SVG viewBox = page dimensions → блоки в page coords автоматически масштабируются.
 * Изолирован от PdfPageCanvas — overlay-изменения не перерендеривают canvas.
 */

import { memo, useRef } from 'react'
import { useShallow } from 'zustand/shallow'

import { useBlockInteraction } from '../../hooks/useBlockInteraction'
import { useEditorStore } from '../../store/useEditorStore'
import { ShapeType } from '../../types/block'
import { BlockLabel } from './BlockLabel'
import { BlockPolygon } from './BlockPolygon'
import { BlockRect } from './BlockRect'
import { DrawingPreview } from './DrawingPreview'
import { PolygonHandles } from './PolygonHandles'
import { ResizeHandles } from './ResizeHandles'
import { SelectionRect } from './SelectionRect'

interface OverlaySvgProps {
  pageNumber: number
  pageWidth: number
  pageHeight: number
  zoom: number
}

export const OverlaySvg = memo(function OverlaySvg({
  pageNumber,
  pageWidth,
  pageHeight,
  zoom,
}: OverlaySvgProps) {
  const svgRef = useRef<SVGSVGElement>(null)

  // Подписка на блоки только этой страницы
  const blocks = useEditorStore(
    useShallow((state) => state.blocksByPage[pageNumber] ?? []),
  )
  const selectedIds = useEditorStore(useShallow((state) => state.selectedIds))

  const {
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handleDoubleClick,
    handleContextMenu,
    handleResizeStart,
    handleVertexStart,
    handleEdgeStart,
  } = useBlockInteraction({
    svgRef,
    pageNumber,
    pageWidth,
    pageHeight,
  })

  // Найти единственный выделенный блок для показа handles
  const selectedBlock =
    selectedIds.size === 1
      ? blocks.find((b) => selectedIds.has(b.id)) ?? null
      : null

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${pageWidth} ${pageHeight}`}
      width={pageWidth * zoom}
      height={pageHeight * zoom}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        pointerEvents: 'all',
      }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onDoubleClick={handleDoubleClick}
      onContextMenu={handleContextMenu}
    >
      {/* Блоки */}
      {blocks.map((block, idx) => {
        const isSelected = selectedIds.has(block.id)
        return block.shapeType === ShapeType.POLYGON && block.polygonJson ? (
          <g key={block.id}>
            <BlockPolygon block={block} isSelected={isSelected} />
            <BlockLabel block={block} index={idx} />
          </g>
        ) : (
          <g key={block.id}>
            <BlockRect block={block} isSelected={isSelected} />
            <BlockLabel block={block} index={idx} />
          </g>
        )
      })}

      {/* Resize handles для единственного выделенного rect блока */}
      {selectedBlock && selectedBlock.shapeType === ShapeType.RECTANGLE && (
        <ResizeHandles
          bbox={selectedBlock.bboxJson}
          onHandlePointerDown={handleResizeStart}
        />
      )}

      {/* Polygon handles для единственного выделенного polygon блока */}
      {selectedBlock &&
        selectedBlock.shapeType === ShapeType.POLYGON &&
        selectedBlock.polygonJson && (
          <PolygonHandles
            points={selectedBlock.polygonJson}
            onVertexPointerDown={handleVertexStart}
            onEdgePointerDown={handleEdgeStart}
          />
        )}

      {/* Drawing preview */}
      <DrawingPreview />

      {/* Selection rubber-band */}
      <SelectionRect />
    </svg>
  )
})
