/**
 * Превью при рисовании нового блока.
 * Rect: красный dashed прямоугольник.
 * Polygon: линии между точками + dashed линия к курсору.
 */

import { memo } from 'react'
import { useShallow } from 'zustand/shallow'

import { useEditorStore } from '../../store/useEditorStore'
import { BLOCK_COLORS } from '../../types/block'
import type { BlockKind } from '../../types/block'
import { InteractionState } from '../../types/editor'

export const DrawingPreview = memo(function DrawingPreview() {
  const { interactionState, drawingOrigin, drawingCurrent, drawingPoints, activeBlockKind } =
    useEditorStore(
      useShallow((s) => ({
        interactionState: s.interactionState,
        drawingOrigin: s.drawingOrigin,
        drawingCurrent: s.drawingCurrent,
        drawingPoints: s.drawingPoints,
        activeBlockKind: s.activeBlockKind,
      })),
    )

  const color = BLOCK_COLORS[activeBlockKind as BlockKind] ?? 'red'

  // Превью rect при рисовании
  if (interactionState === InteractionState.DRAWING_RECT && drawingOrigin && drawingCurrent) {
    const x = Math.min(drawingOrigin.x, drawingCurrent.x)
    const y = Math.min(drawingOrigin.y, drawingCurrent.y)
    const w = Math.abs(drawingCurrent.x - drawingOrigin.x)
    const h = Math.abs(drawingCurrent.y - drawingOrigin.y)

    return (
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        fill={color}
        fillOpacity={0.12}
        stroke={color}
        strokeWidth={2}
        strokeDasharray="6 3"
        style={{ pointerEvents: 'none' }}
      />
    )
  }

  // Превью polygon при рисовании
  if (interactionState === InteractionState.DRAWING_POLYGON && drawingPoints.length > 0) {
    const lines: React.ReactNode[] = []

    // Линии между существующими точками
    for (let i = 0; i < drawingPoints.length - 1; i++) {
      lines.push(
        <line
          key={`line-${i}`}
          x1={drawingPoints[i].x}
          y1={drawingPoints[i].y}
          x2={drawingPoints[i + 1].x}
          y2={drawingPoints[i + 1].y}
          stroke={color}
          strokeWidth={2}
        />,
      )
    }

    // Dashed линия от последней точки к курсору
    if (drawingCurrent) {
      const last = drawingPoints[drawingPoints.length - 1]
      lines.push(
        <line
          key="preview-line"
          x1={last.x}
          y1={last.y}
          x2={drawingCurrent.x}
          y2={drawingCurrent.y}
          stroke={color}
          strokeWidth={2}
          strokeDasharray="6 3"
          strokeOpacity={0.6}
        />,
      )
    }

    // Маркеры на вершинах (красные кружки, из legacy: 6px)
    const markers = drawingPoints.map((pt, i) => (
      <circle
        key={`marker-${i}`}
        cx={pt.x}
        cy={pt.y}
        r={4}
        fill="white"
        stroke={color}
        strokeWidth={2}
      />
    ))

    return (
      <g style={{ pointerEvents: 'none' }}>
        {lines}
        {markers}
      </g>
    )
  }

  return null
})
