/**
 * 8 resize handles для выделенного блока.
 * Из legacy page_viewer_resize.py: 4 угла + 4 середины сторон.
 * Красная рамка, белая заливка, 8px размер.
 */

import { memo, useMemo } from 'react'
import type { BlockCoords } from '../../types/block'
import type { ResizeHandle } from '../../types/editor'
import { HANDLE_SIZE } from '../../types/editor'

interface ResizeHandlesProps {
  bbox: BlockCoords
  onHandlePointerDown: (handle: ResizeHandle, e: React.PointerEvent) => void
}

interface HandleDef {
  id: ResizeHandle
  cx: number
  cy: number
  cursor: string
}

export const ResizeHandles = memo(function ResizeHandles({
  bbox,
  onHandlePointerDown,
}: ResizeHandlesProps) {
  const { x, y, width, height } = bbox
  const hs = HANDLE_SIZE / 2

  const handles = useMemo<HandleDef[]>(
    () => [
      // Углы
      { id: 'tl', cx: x, cy: y, cursor: 'nwse-resize' },
      { id: 'tr', cx: x + width, cy: y, cursor: 'nesw-resize' },
      { id: 'bl', cx: x, cy: y + height, cursor: 'nesw-resize' },
      { id: 'br', cx: x + width, cy: y + height, cursor: 'nwse-resize' },
      // Середины
      { id: 't', cx: x + width / 2, cy: y, cursor: 'ns-resize' },
      { id: 'b', cx: x + width / 2, cy: y + height, cursor: 'ns-resize' },
      { id: 'l', cx: x, cy: y + height / 2, cursor: 'ew-resize' },
      { id: 'r', cx: x + width, cy: y + height / 2, cursor: 'ew-resize' },
    ],
    [x, y, width, height],
  )

  return (
    <g>
      {handles.map((h) => (
        <rect
          key={h.id}
          x={h.cx - hs}
          y={h.cy - hs}
          width={HANDLE_SIZE}
          height={HANDLE_SIZE}
          fill="white"
          stroke="red"
          strokeWidth={1.5}
          style={{ cursor: h.cursor }}
          onPointerDown={(e) => {
            e.stopPropagation()
            onHandlePointerDown(h.id, e)
          }}
        />
      ))}
    </g>
  )
})
