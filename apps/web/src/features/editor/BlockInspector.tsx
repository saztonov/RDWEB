/**
 * Block Inspector — правая панель детальной информации о блоке.
 *
 * Секции:
 * 1. Header: kind, status, lock toggle
 * 2. Content: редактирование current_text
 * 3. Structured: редактирование structured_json (stamp/image)
 * 4. Provenance: source, model, prompt version, attempt id
 * 5. Actions: rerun, accept candidate
 * 6. Attempts: список recognition_attempts
 */

import { useCallback, useEffect, useState } from 'react'
import {
  CheckCircleOutlined,
  CloseOutlined,
  LockOutlined,
  ReloadOutlined,
  UnlockOutlined,
} from '@ant-design/icons'
import {
  Button,
  Collapse,
  Descriptions,
  Divider,
  Empty,
  Input,
  List,
  Space,
  Spin,
  Switch,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { useShallow } from 'zustand/shallow'

import { useEditorStore } from '../../store/useEditorStore'
import type { RecognitionAttempt } from '../../types/block'
import { BlockKind, BLOCK_COLORS } from '../../types/block'

const { Text, Title } = Typography
const { TextArea } = Input

/** Цвет статус-тега */
function statusColor(status: string): string {
  switch (status) {
    case 'recognized':
    case 'success':
      return 'success'
    case 'failed':
    case 'timeout':
      return 'error'
    case 'processing':
    case 'running':
      return 'processing'
    case 'pending':
    case 'queued':
      return 'default'
    case 'manual_review':
      return 'warning'
    default:
      return 'default'
  }
}

export function BlockInspector() {
  const {
    inspectedBlockId,
    inspectedDetail,
    inspectedAttempts,
    inspectorLoading,
  } = useEditorStore(
    useShallow((s) => ({
      inspectedBlockId: s.inspectedBlockId,
      inspectedDetail: s.inspectedDetail,
      inspectedAttempts: s.inspectedAttempts,
      inspectorLoading: s.inspectorLoading,
    })),
  )

  const closeInspector = useEditorStore((s) => s.closeInspector)
  const editBlockContent = useEditorStore((s) => s.editBlockContent)
  const toggleManualLock = useEditorStore((s) => s.toggleManualLock)
  const rerunBlock = useEditorStore((s) => s.rerunBlock)
  const acceptAttempt = useEditorStore((s) => s.acceptAttempt)

  // Локальный state для редактирования текста
  const [editText, setEditText] = useState('')
  const [editDirty, setEditDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  // Синхронизировать текст при смене блока
  useEffect(() => {
    if (inspectedDetail?.block) {
      setEditText(inspectedDetail.block.currentText ?? '')
      setEditDirty(false)
    }
  }, [inspectedDetail?.block?.id, inspectedDetail?.block?.contentRev])

  const handleSaveText = useCallback(async () => {
    if (!inspectedBlockId || !editDirty) return
    setSaving(true)
    try {
      await editBlockContent(inspectedBlockId, editText)
      setEditDirty(false)
    } finally {
      setSaving(false)
    }
  }, [inspectedBlockId, editText, editDirty, editBlockContent])

  const handleToggleLock = useCallback(async () => {
    if (!inspectedDetail?.block) return
    await toggleManualLock(
      inspectedDetail.block.id,
      !inspectedDetail.block.manualLock,
    )
  }, [inspectedDetail, toggleManualLock])

  const handleRerun = useCallback(async () => {
    if (!inspectedBlockId) return
    await rerunBlock(inspectedBlockId)
  }, [inspectedBlockId, rerunBlock])

  const handleAcceptCandidate = useCallback(async () => {
    if (!inspectedBlockId || !inspectedDetail?.pendingCandidate) return
    await acceptAttempt(inspectedBlockId, inspectedDetail.pendingCandidate.id)
  }, [inspectedBlockId, inspectedDetail, acceptAttempt])

  const handleAcceptAttempt = useCallback(
    async (attemptId: string) => {
      if (!inspectedBlockId) return
      await acceptAttempt(inspectedBlockId, attemptId)
    },
    [inspectedBlockId, acceptAttempt],
  )

  if (!inspectedBlockId) return null

  const block = inspectedDetail?.block
  const attempt = inspectedDetail?.currentAttempt
  const candidate = inspectedDetail?.pendingCandidate

  return (
    <div
      style={{
        width: 350,
        borderLeft: '1px solid #d9d9d9',
        backgroundColor: '#fafafa',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '12px 16px',
          borderBottom: '1px solid #f0f0f0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <Space>
          {block && (
            <>
              <div
                style={{
                  width: 12,
                  height: 12,
                  borderRadius: 2,
                  backgroundColor: BLOCK_COLORS[block.blockKind],
                  border: '1px solid rgba(0,0,0,0.15)',
                }}
              />
              <Text strong style={{ fontSize: 14 }}>
                {block.blockKind}
              </Text>
              <Tag color={statusColor(block.currentStatus)}>
                {block.currentStatus}
              </Tag>
            </>
          )}
        </Space>
        <Button
          type="text"
          size="small"
          icon={<CloseOutlined />}
          onClick={closeInspector}
        />
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflow: 'auto', padding: '0 16px 16px' }}>
        {inspectorLoading ? (
          <div style={{ textAlign: 'center', marginTop: 48 }}>
            <Spin />
          </div>
        ) : block ? (
          <>
            {/* Lock toggle */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '12px 0',
              }}
            >
              <Space>
                {block.manualLock ? (
                  <LockOutlined style={{ color: '#faad14' }} />
                ) : (
                  <UnlockOutlined style={{ color: '#8c8c8c' }} />
                )}
                <Text>Manual Lock</Text>
              </Space>
              <Switch
                checked={block.manualLock}
                onChange={handleToggleLock}
                size="small"
              />
            </div>

            <Divider style={{ margin: '0 0 12px' }} />

            {/* Content editing */}
            <div style={{ marginBottom: 16 }}>
              <Text strong style={{ display: 'block', marginBottom: 8 }}>
                Текст блока
              </Text>
              <TextArea
                value={editText}
                onChange={(e) => {
                  setEditText(e.target.value)
                  setEditDirty(true)
                }}
                rows={6}
                style={{ fontFamily: 'monospace', fontSize: 12 }}
              />
              <Button
                type="primary"
                size="small"
                disabled={!editDirty}
                loading={saving}
                onClick={handleSaveText}
                style={{ marginTop: 8 }}
              >
                Сохранить
              </Button>
              {editDirty && (
                <Text
                  type="warning"
                  style={{ marginLeft: 8, fontSize: 12 }}
                >
                  Есть несохранённые изменения
                </Text>
              )}
            </div>

            {/* Structured JSON для stamp/image */}
            {block.currentStructuredJson &&
              (block.blockKind === BlockKind.STAMP ||
                block.blockKind === BlockKind.IMAGE) && (
                <div style={{ marginBottom: 16 }}>
                  <Text strong style={{ display: 'block', marginBottom: 8 }}>
                    Structured данные
                  </Text>
                  <Descriptions
                    column={1}
                    size="small"
                    bordered
                    style={{ fontSize: 12 }}
                  >
                    {Object.entries(block.currentStructuredJson).map(
                      ([key, value]) => (
                        <Descriptions.Item key={key} label={key}>
                          {typeof value === 'string'
                            ? value
                            : JSON.stringify(value)}
                        </Descriptions.Item>
                      ),
                    )}
                  </Descriptions>
                </div>
              )}

            <Divider style={{ margin: '0 0 12px' }} />

            {/* Provenance */}
            <div style={{ marginBottom: 16 }}>
              <Text strong style={{ display: 'block', marginBottom: 8 }}>
                Provenance
              </Text>
              {attempt ? (
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="Source">
                    {attempt.sourceName ?? attempt.sourceId ?? '—'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Model">
                    {attempt.modelName ?? '—'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Prompt">
                    {attempt.promptKey
                      ? `${attempt.promptKey} v${attempt.promptVersion}`
                      : '—'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Attempt">
                    #{attempt.attemptNo ?? '—'}
                    {attempt.fallbackNo > 0 &&
                      ` (fallback ${attempt.fallbackNo})`}
                  </Descriptions.Item>
                  <Descriptions.Item label="Время">
                    {attempt.finishedAt
                      ? new Date(attempt.finishedAt).toLocaleString()
                      : '—'}
                  </Descriptions.Item>
                </Descriptions>
              ) : (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Ещё не распознан
                </Text>
              )}
            </div>

            {/* Revisions info */}
            <Descriptions column={2} size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="geometry_rev">
                {block.geometryRev}
              </Descriptions.Item>
              <Descriptions.Item label="content_rev">
                {block.contentRev}
              </Descriptions.Item>
            </Descriptions>

            <Divider style={{ margin: '0 0 12px' }} />

            {/* Actions */}
            <Space direction="vertical" style={{ width: '100%', marginBottom: 16 }}>
              <Button
                icon={<ReloadOutlined />}
                onClick={handleRerun}
                block
              >
                Перезапустить блок
              </Button>

              {/* Accept candidate */}
              {candidate && block.manualLock && (
                <Button
                  type="primary"
                  icon={<CheckCircleOutlined />}
                  onClick={handleAcceptCandidate}
                  block
                >
                  Принять результат ({candidate.modelName ?? 'OCR'})
                </Button>
              )}
            </Space>

            {/* Pending candidate preview */}
            {candidate && (
              <div
                style={{
                  padding: '8px 12px',
                  backgroundColor: '#fffbe6',
                  border: '1px solid #ffe58f',
                  borderRadius: 4,
                  marginBottom: 16,
                }}
              >
                <Text strong style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                  Ожидающий результат
                </Text>
                <Text style={{ fontSize: 12 }}>
                  {(candidate.normalizedText ?? '').slice(0, 200)}
                  {(candidate.normalizedText ?? '').length > 200 && '...'}
                </Text>
              </div>
            )}

            <Divider style={{ margin: '0 0 12px' }} />

            {/* Attempts history */}
            <Collapse
              size="small"
              items={[
                {
                  key: 'attempts',
                  label: `Попытки распознавания (${inspectedDetail?.attemptsCount ?? 0})`,
                  children:
                    inspectedAttempts.length === 0 ? (
                      <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description="Нет попыток"
                      />
                    ) : (
                      <List
                        size="small"
                        dataSource={inspectedAttempts}
                        renderItem={(att: RecognitionAttempt) => (
                          <List.Item
                            style={{ padding: '6px 0' }}
                            actions={
                              att.status === 'success' &&
                              !att.selectedAsCurrent
                                ? [
                                    <Tooltip
                                      key="accept"
                                      title="Принять как текущий"
                                    >
                                      <Button
                                        size="small"
                                        type="link"
                                        icon={<CheckCircleOutlined />}
                                        onClick={() =>
                                          handleAcceptAttempt(att.id)
                                        }
                                      />
                                    </Tooltip>,
                                  ]
                                : undefined
                            }
                          >
                            <Space
                              direction="vertical"
                              size={0}
                              style={{ width: '100%' }}
                            >
                              <Space>
                                <Text style={{ fontSize: 12 }}>
                                  #{att.attemptNo}
                                </Text>
                                <Tag
                                  color={statusColor(att.status)}
                                  style={{ fontSize: 10 }}
                                >
                                  {att.status}
                                </Tag>
                                {att.selectedAsCurrent && (
                                  <Tag color="blue" style={{ fontSize: 10 }}>
                                    current
                                  </Tag>
                                )}
                              </Space>
                              <Text
                                type="secondary"
                                style={{ fontSize: 11 }}
                              >
                                {att.modelName ?? '—'} ·{' '}
                                {att.createdAt
                                  ? new Date(att.createdAt).toLocaleString()
                                  : '—'}
                              </Text>
                              {att.normalizedText && (
                                <Text
                                  style={{
                                    fontSize: 11,
                                    color: '#595959',
                                    display: 'block',
                                    marginTop: 2,
                                  }}
                                >
                                  {att.normalizedText.slice(0, 100)}
                                  {att.normalizedText.length > 100 && '...'}
                                </Text>
                              )}
                            </Space>
                          </List.Item>
                        )}
                      />
                    ),
                },
              ]}
            />
          </>
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="Блок не найден"
            style={{ marginTop: 48 }}
          />
        )}
      </div>
    </div>
  )
}
