/**
 * SVG circle handles для вершин polygon блока.
 * Из legacy page_viewer_polygon.py: белые кружки с красной рамкой.
 */

import { memo } from 'react'

interface PolygonHandlesProps {
  points: [number, number][]
  onVertexPointerDown: (vertexIdx: number, e: React.PointerEvent) => void
  onEdgePointerDown: (edgeIdx: number, e: React.PointerEvent) => void
}

export const PolygonHandles = memo(function PolygonHandles({
  points,
  onVertexPointerDown,
  onEdgePointerDown,
}: PolygonHandlesProps) {
  if (points.length < 2) return null

  return (
    <g>
      {/* Невидимые толстые линии для edge hit testing (12px зона) */}
      {points.map(([x1, y1], i) => {
        const [x2, y2] = points[(i + 1) % points.length]
        return (
          <line
            key={`edge-hit-${i}`}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke="transparent"
            strokeWidth={12}
            style={{ cursor: 'move' }}
            onPointerDown={(e) => {
              e.stopPropagation()
              onEdgePointerDown(i, e)
            }}
          />
        )
      })}

      {/* Vertex handles */}
      {points.map(([cx, cy], i) => (
        <circle
          key={`vertex-${i}`}
          cx={cx}
          cy={cy}
          r={5}
          fill="white"
          stroke="red"
          strokeWidth={1.5}
          style={{ cursor: 'move' }}
          onPointerDown={(e) => {
            e.stopPropagation()
            onVertexPointerDown(i, e)
          }}
        />
      ))}
    </g>
  )
})
