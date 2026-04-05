/**
 * SVG <text> — номер блока (1-indexed), top-right угол bbox.
 * Из legacy: красный bold, Arial 12pt, offset 5px от угла.
 * + иконки: замок (locked), молния (dirty).
 */

import { memo } from 'react'
import type { Block } from '../../types/block'

interface BlockLabelProps {
  block: Block
  index: number
}

export const BlockLabel = memo(function BlockLabel({ block, index }: BlockLabelProps) {
  const { x, y, width } = block.bboxJson

  // Индикаторы после номера
  const isDirty =
    !block.lastRecognitionSignature && block.currentStatus !== 'pending'

  return (
    <g style={{ pointerEvents: 'none' }}>
      <text
        x={x + width - 5}
        y={y + 14}
        fill="red"
        fontSize={12}
        fontWeight="bold"
        fontFamily="Arial, sans-serif"
        textAnchor="end"
      >
        {index + 1}
      </text>
      {/* Замок — locked-блок */}
      {block.manualLock && (
        <text
          x={x + 5}
          y={y + 14}
          fill="#faad14"
          fontSize={11}
          fontFamily="Arial, sans-serif"
        >
          🔒
        </text>
      )}
      {/* Молния — dirty-блок */}
      {isDirty && (
        <text
          x={x + (block.manualLock ? 20 : 5)}
          y={y + 14}
          fill="#fa8c16"
          fontSize={11}
          fontFamily="Arial, sans-serif"
        >
          ⚡
        </text>
      )}
    </g>
  )
})
