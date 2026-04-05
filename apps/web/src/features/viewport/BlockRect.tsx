/**
 * SVG <rect> для rectangle-блока.
 * Цвета из legacy page_viewer_blocks.py: text=green, image=orange, stamp=dodgerblue.
 */

import { memo } from 'react'
import type { Block } from '../../types/block'
import { BLOCK_COLORS, SELECTION_COLOR } from '../../types/block'

interface BlockRectProps {
  block: Block
  isSelected: boolean
}

export const BlockRect = memo(function BlockRect({ block, isSelected }: BlockRectProps) {
  const color = isSelected ? SELECTION_COLOR : BLOCK_COLORS[block.blockKind]
  const strokeWidth = isSelected ? 4 : 2
  const { x, y, width, height } = block.bboxJson

  return (
    <rect
      x={x}
      y={y}
      width={width}
      height={height}
      fill={color}
      fillOpacity={0.12}
      stroke={color}
      strokeWidth={strokeWidth}
      data-block-id={block.id}
      style={{ cursor: 'pointer' }}
    />
  )
})
