/**
 * Sidebar редактора: список блоков текущей страницы + фильтры.
 * Ant Design компоненты для фильтров по kind, status, source, model.
 */

import { useCallback, useMemo, useState } from 'react'
import {
  DeleteOutlined,
  LockOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { Button, Empty, List, Select, Space, Tag, Tooltip, Typography } from 'antd'
import { useShallow } from 'zustand/shallow'

import { useEditorStore } from '../../store/useEditorStore'
import { selectBlocksForCurrentPage } from '../../store/selectors'
import type { BlockKind, BlockStatus } from '../../types/block'
import { BLOCK_COLORS } from '../../types/block'

const { Text } = Typography

const KIND_OPTIONS = [
  { value: 'text', label: 'Text' },
  { value: 'stamp', label: 'Stamp' },
  { value: 'image', label: 'Image' },
]

const STATUS_OPTIONS = [
  { value: 'pending', label: 'Pending' },
  { value: 'queued', label: 'Queued' },
  { value: 'processing', label: 'Processing' },
  { value: 'recognized', label: 'Recognized' },
  { value: 'failed', label: 'Failed' },
  { value: 'manual_review', label: 'Manual Review' },
  { value: 'skipped', label: 'Skipped' },
]

export function EditorSidebar() {
  const blocks = useEditorStore(selectBlocksForCurrentPage)
  const selectedIds = useEditorStore(useShallow((s) => s.selectedIds))
  const selectBlock = useEditorStore((s) => s.selectBlock)
  const softDeleteBlock = useEditorStore((s) => s.softDeleteBlock)
  const openInspector = useEditorStore((s) => s.openInspector)
  const currentPage = useEditorStore((s) => s.currentPage)

  // Фильтры
  const [kindFilter, setKindFilter] = useState<BlockKind | null>(null)
  const [statusFilter, setStatusFilter] = useState<BlockStatus | null>(null)

  const filteredBlocks = useMemo(() => {
    let result = blocks
    if (kindFilter) {
      result = result.filter((b) => b.blockKind === kindFilter)
    }
    if (statusFilter) {
      result = result.filter((b) => b.currentStatus === statusFilter)
    }
    return result
  }, [blocks, kindFilter, statusFilter])

  const handleBlockClick = useCallback(
    (blockId: string) => {
      selectBlock(blockId)
    },
    [selectBlock],
  )

  const handleBlockDoubleClick = useCallback(
    (blockId: string) => {
      selectBlock(blockId)
      openInspector(blockId)
    },
    [selectBlock, openInspector],
  )

  const handleDelete = useCallback(
    (blockId: string, e: React.MouseEvent) => {
      e.stopPropagation()
      softDeleteBlock(blockId)
    },
    [softDeleteBlock],
  )

  return (
    <div
      style={{
        width: 280,
        borderRight: '1px solid #d9d9d9',
        backgroundColor: '#fafafa',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid #f0f0f0' }}>
        <Text strong>
          Блоки — стр. {currentPage} ({blocks.length})
        </Text>
      </div>

      {/* Фильтры */}
      <div style={{ padding: '8px 16px', borderBottom: '1px solid #f0f0f0' }}>
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          <Select
            allowClear
            placeholder="Тип блока"
            options={KIND_OPTIONS}
            value={kindFilter}
            onChange={setKindFilter}
            style={{ width: '100%' }}
            size="small"
          />
          <Select
            allowClear
            placeholder="Статус"
            options={STATUS_OPTIONS}
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: '100%' }}
            size="small"
          />
        </Space>
      </div>

      {/* Список блоков */}
      <div style={{ flex: 1, overflow: 'auto', padding: '0 8px' }}>
        {filteredBlocks.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="Нет блоков"
            style={{ marginTop: 32 }}
          />
        ) : (
          <List
            size="small"
            dataSource={filteredBlocks}
            renderItem={(block, index) => {
              const isSelected = selectedIds.has(block.id)
              const color = BLOCK_COLORS[block.blockKind]
              return (
                <List.Item
                  onClick={() => handleBlockClick(block.id)}
                  onDoubleClick={() => handleBlockDoubleClick(block.id)}
                  style={{
                    cursor: 'pointer',
                    backgroundColor: isSelected ? '#e6f4ff' : undefined,
                    borderRadius: 4,
                    padding: '6px 8px',
                    marginBottom: 2,
                  }}
                  actions={[
                    <Button
                      key="delete"
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={(e) => handleDelete(block.id, e)}
                    />,
                  ]}
                >
                  <Space>
                    <div
                      style={{
                        width: 12,
                        height: 12,
                        borderRadius: 2,
                        backgroundColor: color,
                        border: '1px solid rgba(0,0,0,0.15)',
                      }}
                    />
                    <Text style={{ fontSize: 13 }}>
                      #{index + 1} {block.blockKind}
                    </Text>
                    <Tag
                      color={
                        block.currentStatus === 'recognized'
                          ? 'success'
                          : block.currentStatus === 'failed'
                            ? 'error'
                            : 'default'
                      }
                      style={{ fontSize: 11 }}
                    >
                      {block.currentStatus}
                    </Tag>
                    {block.manualLock && (
                      <Tooltip title="Manual lock — защита от перезаписи">
                        <LockOutlined style={{ color: '#faad14', fontSize: 12 }} />
                      </Tooltip>
                    )}
                    {!block.lastRecognitionSignature && block.currentStatus !== 'pending' && (
                      <Tooltip title="Dirty — требует перераспознавания">
                        <WarningOutlined style={{ color: '#fa8c16', fontSize: 12 }} />
                      </Tooltip>
                    )}
                  </Space>
                </List.Item>
              )
            }}
          />
        )}
      </div>
    </div>
  )
}
