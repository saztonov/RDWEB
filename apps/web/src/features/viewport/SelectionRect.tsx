/**
 * Rubber-band прямоугольник выделения.
 * Из legacy: синий dashed 2px, полупрозрачная заливка.
 */

import { memo } from 'react'
import { useShallow } from 'zustand/shallow'

import { useEditorStore } from '../../store/useEditorStore'
import { SELECTION_COLOR } from '../../types/block'
import { InteractionState } from '../../types/editor'

export const SelectionRect = memo(function SelectionRect() {
  const { interactionState, drawingOrigin, drawingCurrent } = useEditorStore(
    useShallow((s) => ({
      interactionState: s.interactionState,
      drawingOrigin: s.drawingOrigin,
      drawingCurrent: s.drawingCurrent,
    })),
  )

  if (interactionState !== InteractionState.SELECTING || !drawingOrigin || !drawingCurrent) {
    return null
  }

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
      fill={SELECTION_COLOR}
      fillOpacity={0.12}
      stroke={SELECTION_COLOR}
      strokeWidth={2}
      strokeDasharray="6 3"
      style={{ pointerEvents: 'none' }}
    />
  )
})
