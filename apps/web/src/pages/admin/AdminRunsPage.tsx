/**
 * Admin Recognition Runs — список run-ов с фильтрами и прогрессом.
 */

import { useEffect } from 'react'
import { Table, Tag, Progress, Space, Typography, Select, Input, Button } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useNavigate } from 'react-router-dom'
import { useAdminStore } from '../../store/useAdminStore'
import type { AdminRun } from '../../api/adminApi'

const { Title, Text } = Typography

const statusColors: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  completed: 'success',
  failed: 'error',
  cancelled: 'warning',
}

const statusEmoji: Record<string, string> = {
  pending: '\u23f3',
  running: '\ud83d\udd04',
  completed: '\u2705',
  failed: '\u274c',
  cancelled: '\ud83d\udeab',
}

function formatDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) return '-'
  const start = new Date(startedAt).getTime()
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now()
  const seconds = Math.round((end - start) / 1000)
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}

export default function AdminRunsPage() {
  const {
    runs, runsMeta, runsLoading, runsFilters,
    loadRuns,
  } = useAdminStore()
  const navigate = useNavigate()

  useEffect(() => {
    loadRuns()
  }, [loadRuns])

  const columns: ColumnsType<AdminRun> = [
    {
      title: 'Run ID',
      dataIndex: 'id',
      key: 'id',
      width: 100,
      render: (id: string) => (
        <Typography.Text copyable={{ text: id }} style={{ fontSize: 12 }}>
          {id.slice(0, 8)}...
        </Typography.Text>
      ),
    },
    {
      title: 'Document',
      dataIndex: 'documentTitle',
      key: 'document',
      ellipsis: true,
      render: (title: string | null, record) => title ?? record.documentId.slice(0, 8),
    },
    {
      title: 'Mode',
      dataIndex: 'runMode',
      key: 'runMode',
      width: 100,
      render: (mode: string) => <Tag>{mode}</Tag>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 130,
      render: (status: string) => (
        <Tag color={statusColors[status] ?? 'default'}>
          {statusEmoji[status] ?? ''} {status}
        </Tag>
      ),
    },
    {
      title: 'Progress',
      key: 'progress',
      width: 180,
      render: (_, record) => {
        const total = record.totalBlocks || 1
        const processed = record.processedBlocks
        const percent = Math.round((processed / total) * 100)
        const color = record.status === 'failed' ? '#ff4d4f' : record.status === 'completed' ? '#52c41a' : '#1890ff'
        return (
          <Space direction="vertical" size={0} style={{ width: '100%' }}>
            <Progress percent={percent} size="small" strokeColor={color} />
            <Text type="secondary" style={{ fontSize: 11 }}>
              {processed}/{total}
            </Text>
          </Space>
        )
      },
    },
    {
      title: 'Counters',
      key: 'counters',
      width: 200,
      render: (_, record) => (
        <Space size={4} wrap>
          <Tag color="green">{record.recognizedBlocks} rec</Tag>
          <Tag color="red">{record.failedBlocks} fail</Tag>
          <Tag color="orange">{record.manualReviewBlocks} review</Tag>
        </Space>
      ),
    },
    {
      title: 'Duration',
      key: 'duration',
      width: 100,
      render: (_, record) => formatDuration(record.startedAt, record.finishedAt),
    },
    {
      title: 'Created',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 160,
      render: (date: string) => new Date(date).toLocaleString(),
      sorter: (a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
      defaultSortOrder: 'descend',
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>Recognition Runs</Title>
        <Button icon={<ReloadOutlined />} onClick={() => loadRuns()}>Refresh</Button>
      </Space>

      {/* Фильтры */}
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          placeholder="Status"
          allowClear
          style={{ width: 150 }}
          value={runsFilters.status ?? undefined}
          onChange={(val) => loadRuns({ ...runsFilters, status: val ?? undefined, offset: 0 })}
          options={[
            { value: 'pending', label: '\u23f3 pending' },
            { value: 'running', label: '\ud83d\udd04 running' },
            { value: 'completed', label: '\u2705 completed' },
            { value: 'failed', label: '\u274c failed' },
            { value: 'cancelled', label: '\ud83d\udeab cancelled' },
          ]}
        />
        <Input.Search
          placeholder="Document ID"
          allowClear
          style={{ width: 280 }}
          onSearch={(val) => loadRuns({ ...runsFilters, documentId: val || undefined, offset: 0 })}
        />
      </Space>

      <Table
        columns={columns}
        dataSource={runs}
        rowKey="id"
        loading={runsLoading}
        size="small"
        pagination={{
          total: runsMeta?.total ?? 0,
          pageSize: runsFilters.limit ?? 50,
          current: Math.floor((runsFilters.offset ?? 0) / (runsFilters.limit ?? 50)) + 1,
          onChange: (page, pageSize) => {
            loadRuns({ ...runsFilters, limit: pageSize, offset: (page - 1) * pageSize })
          },
          showSizeChanger: true,
          showTotal: (total) => `${total} runs`,
        }}
        onRow={(record) => ({
          onClick: () => navigate(`/admin/runs/${record.id}`),
          style: { cursor: 'pointer' },
        })}
      />
    </div>
  )
}
