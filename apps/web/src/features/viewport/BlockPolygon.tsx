/**
 * SVG <polygon> для polygon-блока.
 * Рендерит polygon_json как SVG polygon с заливкой и обводкой.
 */

import { memo } from 'react'
import type { Block } from '../../types/block'
import { BLOCK_COLORS, SELECTION_COLOR } from '../../types/block'

interface BlockPolygonProps {
  block: Block
  isSelected: boolean
}

export const BlockPolygon = memo(function BlockPolygon({ block, isSelected }: BlockPolygonProps) {
  if (!block.polygonJson || block.polygonJson.length < 3) return null

  const color = isSelected ? SELECTION_COLOR : BLOCK_COLORS[block.blockKind]
  const strokeWidth = isSelected ? 4 : 2
  const points = block.polygonJson.map(([x, y]) => `${x},${y}`).join(' ')

  return (
    <polygon
      points={points}
      fill={color}
      fillOpacity={0.12}
      stroke={color}
      strokeWidth={strokeWidth}
      data-block-id={block.id}
      style={{ cursor: 'pointer' }}
    />
  )
})
