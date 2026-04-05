/**
 * Admin Run Detail — детали recognition run-а с блоками.
 */

import { useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Card, Col, Row, Spin, Table, Tag, Space, Typography, Statistic, Button, Progress } from 'antd'
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useAdminStore } from '../../store/useAdminStore'
import { useAdminSSE } from '../../hooks/useAdminSSE'
import type { AdminRunBlock } from '../../api/adminApi'

const { Title, Text } = Typography

const statusColors: Record<string, string> = {
  pending: 'default',
  queued: 'default',
  processing: 'processing',
  recognized: 'success',
  failed: 'error',
  manual_review: 'warning',
  skipped: 'default',
}

export default function AdminRunDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { selectedRun, selectedRunLoading, loadRunDetail } = useAdminStore()

  useEffect(() => {
    if (id) loadRunDetail(id)
  }, [id, loadRunDetail])

  // SSE: перезагрузить при обновлении runs
  useAdminSSE({
    onRuns: () => {
      if (id) loadRunDetail(id)
    },
  }, selectedRun?.status === 'running')

  if (selectedRunLoading && !selectedRun) {
    return <Spin size="large" style={{ display: 'flex', justifyContent: 'center', marginTop: 80 }} />
  }

  if (!selectedRun) {
    return <Text type="secondary">Run не найден</Text>
  }

  const run = selectedRun
  const total = run.totalBlocks || 1
  const percent = Math.round((run.processedBlocks / total) * 100)

  // ETA
  let eta = ''
  if (run.status === 'running' && run.startedAt && run.processedBlocks > 0) {
    const elapsed = (Date.now() - new Date(run.startedAt).getTime()) / 1000
    const remaining = ((total - run.processedBlocks) * elapsed) / run.processedBlocks
    if (remaining > 0) {
      const mins = Math.floor(remaining / 60)
      const secs = Math.round(remaining % 60)
      eta = `~${mins}m ${secs}s remaining`
    }
  }

  const blockColumns: ColumnsType<AdminRunBlock> = [
    {
      title: 'Page',
      dataIndex: 'pageNumber',
      key: 'page',
      width: 70,
      sorter: (a, b) => a.pageNumber - b.pageNumber,
    },
    {
      title: 'Block ID',
      dataIndex: 'blockId',
      key: 'blockId',
      render: (id: string) => (
        <Typography.Text copyable={{ text: id }} style={{ fontSize: 12 }}>
          {id.slice(0, 8)}...
        </Typography.Text>
      ),
    },
    {
      title: 'Kind',
      dataIndex: 'blockKind',
      key: 'kind',
      width: 80,
      render: (kind: string) => <Tag>{kind}</Tag>,
    },
    {
      title: 'Status',
      dataIndex: 'currentStatus',
      key: 'status',
      width: 130,
      render: (status: string) => <Tag color={statusColors[status] ?? 'default'}>{status}</Tag>,
    },
    {
      title: 'Attempts',
      dataIndex: 'attemptCount',
      key: 'attempts',
      width: 80,
    },
    {
      title: 'Last Error',
      dataIndex: 'lastError',
      key: 'error',
      ellipsis: true,
      render: (error: string | null) =>
        error ? <Text type="danger" ellipsis>{error}</Text> : <Text type="secondary">-</Text>,
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/admin/runs')}>
          Back
        </Button>
        <Title level={3} style={{ margin: 0 }}>Run Detail</Title>
        <Tag color={statusColors[run.status] ?? 'default'}>{run.status}</Tag>
        <Button icon={<ReloadOutlined />} size="small" onClick={() => id && loadRunDetail(id)} />
      </Space>

      {/* Summary Cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} md={16}>
          <Card size="small">
            <Row gutter={16}>
              <Col span={4}><Statistic title="Total" value={run.totalBlocks} /></Col>
              <Col span={4}><Statistic title="Dirty" value={run.dirtyBlocks} /></Col>
              <Col span={4}><Statistic title="Processed" value={run.processedBlocks} /></Col>
              <Col span={4}>
                <Statistic title="Recognized" value={run.recognizedBlocks} valueStyle={{ color: '#3f8600' }} />
              </Col>
              <Col span={4}>
                <Statistic title="Failed" value={run.failedBlocks} valueStyle={{ color: '#cf1322' }} />
              </Col>
              <Col span={4}>
                <Statistic title="Review" value={run.manualReviewBlocks} valueStyle={{ color: '#d4b106' }} />
              </Col>
            </Row>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card size="small">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Progress
                percent={percent}
                strokeColor={run.status === 'failed' ? '#ff4d4f' : run.status === 'completed' ? '#52c41a' : '#1890ff'}
              />
              {eta && <Text type="secondary">{eta}</Text>}
              <Space direction="vertical" size={0}>
                <Text type="secondary">Document: {run.documentTitle ?? run.documentId.slice(0, 8)}</Text>
                <Text type="secondary">Mode: {run.runMode}</Text>
                {run.startedAt && <Text type="secondary">Started: {new Date(run.startedAt).toLocaleString()}</Text>}
              </Space>
            </Space>
          </Card>
        </Col>
      </Row>

      {/* Block-level table */}
      <Title level={5}>Blocks ({run.blocks.length})</Title>
      <Table
        columns={blockColumns}
        dataSource={run.blocks}
        rowKey="blockId"
        size="small"
        pagination={{ pageSize: 50, showSizeChanger: true }}
      />
    </div>
  )
}
