/**
 * Toolbar редактора: выбор типа блока, toggle формы, zoom, навигация.
 */

import {
  BorderOutlined,
  DownloadOutlined,
  FileTextOutlined,
  MinusOutlined,
  PictureOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
  StarOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { Button, Dropdown, message, Modal, Segmented, Space, Tag, Tooltip, Typography } from 'antd'
import { useShallow } from 'zustand/shallow'

import { exportDocument } from '../../api/documentsApi'
import { useEditorStore } from '../../store/useEditorStore'
import { BlockKind, ShapeType } from '../../types/block'
import { InteractionState } from '../../types/editor'

const { Text } = Typography

const kindOptions = [
  { value: BlockKind.TEXT, label: 'Text', icon: <FileTextOutlined /> },
  { value: BlockKind.IMAGE, label: 'Image', icon: <PictureOutlined /> },
  { value: BlockKind.STAMP, label: 'Stamp', icon: <SafetyCertificateOutlined /> },
]

export function EditorToolbar() {
  const {
    documentId,
    activeBlockKind,
    activeShapeType,
    currentPage,
    totalPages,
    zoom,
    interactionState,
    saving,
    dirtyCount,
    activeRunId,
    runProgress,
  } = useEditorStore(
    useShallow((s) => ({
      documentId: s.documentId,
      activeBlockKind: s.activeBlockKind,
      activeShapeType: s.activeShapeType,
      currentPage: s.currentPage,
      totalPages: s.totalPages,
      zoom: s.zoom,
      interactionState: s.interactionState,
      saving: s.saving,
      dirtyCount: s.dirtyBlockIds.size,
      activeRunId: s.activeRunId,
      runProgress: s.runProgress,
    })),
  )

  const setActiveBlockKind = useEditorStore((s) => s.setActiveBlockKind)
  const toggleShapeType = useEditorStore((s) => s.toggleShapeType)
  const prevPage = useEditorStore((s) => s.prevPage)
  const nextPage = useEditorStore((s) => s.nextPage)
  const zoomIn = useEditorStore((s) => s.zoomIn)
  const zoomOut = useEditorStore((s) => s.zoomOut)
  const startRecognition = useEditorStore((s) => s.startRecognition)

  const handleExport = async (format: 'html' | 'markdown') => {
    if (!documentId) return
    try {
      await exportDocument(documentId, format)
      message.success(`Экспорт ${format.toUpperCase()} скачан`)
    } catch (err) {
      message.error(err instanceof Error ? err.message : 'Ошибка экспорта')
    }
  }

  const handleSmartRerun = () => startRecognition('smart')
  const handleFullRerun = () => {
    Modal.confirm({
      title: 'Полный перезапуск OCR',
      content: 'Все предыдущие результаты (кроме locked-блоков) будут перезаписаны. Продолжить?',
      okText: 'Запустить',
      okType: 'danger',
      cancelText: 'Отмена',
      onOk: () => startRecognition('full'),
    })
  }

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '8px 16px',
        borderBottom: '1px solid #d9d9d9',
        backgroundColor: '#fff',
      }}
    >
      {/* Левая часть: тип блока + форма */}
      <Space size="middle">
        <Segmented
          options={kindOptions}
          value={activeBlockKind}
          onChange={(val) => setActiveBlockKind(val as BlockKind)}
        />
        <Tooltip title="Переключить rect/polygon (Ctrl+Q)">
          <Button
            icon={activeShapeType === ShapeType.RECTANGLE ? <BorderOutlined /> : <StarOutlined />}
            onClick={toggleShapeType}
          >
            {activeShapeType === ShapeType.RECTANGLE ? 'Rect' : 'Polygon'}
          </Button>
        </Tooltip>
        {interactionState !== InteractionState.IDLE && (
          <Tag color="processing">{interactionState}</Tag>
        )}
      </Space>

      {/* Центр: навигация по страницам */}
      <Space>
        <Button size="small" onClick={prevPage} disabled={currentPage <= 1}>
          ←
        </Button>
        <Text>
          {currentPage} / {totalPages}
        </Text>
        <Button size="small" onClick={nextPage} disabled={currentPage >= totalPages}>
          →
        </Button>
      </Space>

      {/* Центр-правая часть: recognition */}
      <Space>
        <Tooltip title="Smart Rerun — только изменённые блоки">
          <Button
            icon={<ThunderboltOutlined />}
            onClick={handleSmartRerun}
            disabled={!!activeRunId}
          >
            Smart
          </Button>
        </Tooltip>
        <Tooltip title="Full Rerun — все блоки (кроме locked)">
          <Button
            icon={<PlayCircleOutlined />}
            onClick={handleFullRerun}
            disabled={!!activeRunId}
          >
            Full
          </Button>
        </Tooltip>
        {runProgress && (
          <Tag color="processing">
            {runProgress.processedBlocks}/{runProgress.totalBlocks}
          </Tag>
        )}
      </Space>

      {/* Export */}
      <Dropdown
        menu={{
          items: [
            { key: 'html', label: 'HTML' },
            { key: 'markdown', label: 'Markdown' },
          ],
          onClick: ({ key }) => handleExport(key as 'html' | 'markdown'),
        }}
      >
        <Button icon={<DownloadOutlined />}>Export</Button>
      </Dropdown>

      {/* Правая часть: zoom + статус сохранения */}
      <Space>
        <Button icon={<MinusOutlined />} size="small" onClick={zoomOut} />
        <Text style={{ minWidth: 48, textAlign: 'center' }}>
          {Math.round(zoom * 100)}%
        </Text>
        <Button icon={<PlusOutlined />} size="small" onClick={zoomIn} />
        {saving && <Tag color="warning">Сохранение...</Tag>}
        {!saving && dirtyCount > 0 && (
          <Tag color="orange">Несохранённых: {dirtyCount}</Tag>
        )}
      </Space>
    </div>
  )
}
