/**
 * Admin OCR Sources — список source-ов с healthcheck и моделями.
 */

import { useEffect, useState } from 'react'
import { Table, Tag, Button, Space, Typography, Tooltip, Drawer, Descriptions, List } from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useAdminStore } from '../../store/useAdminStore'
import type { AdminOcrSource, AdminOcrSourceDetail } from '../../api/adminApi'
import { fetchAdminSourceDetail } from '../../api/adminApi'

const { Title, Text } = Typography

const statusColors: Record<string, string> = {
  healthy: 'success',
  degraded: 'warning',
  unavailable: 'error',
  unknown: 'default',
}

const statusIcons: Record<string, React.ReactNode> = {
  healthy: <CheckCircleOutlined />,
  degraded: <ExclamationCircleOutlined />,
  unavailable: <CloseCircleOutlined />,
}

export default function AdminSourcesPage() {
  const { sources, sourcesLoading, loadSources, triggerHealthcheck } = useAdminStore()
  const [healthcheckLoading, setHealthcheckLoading] = useState<string | null>(null)
  const [drawerSource, setDrawerSource] = useState<AdminOcrSourceDetail | null>(null)
  const [drawerLoading, setDrawerLoading] = useState(false)

  useEffect(() => {
    loadSources()
  }, [loadSources])

  const handleHealthcheck = async (sourceId: string) => {
    setHealthcheckLoading(sourceId)
    await triggerHealthcheck(sourceId)
    setHealthcheckLoading(null)
  }

  const handleShowDetail = async (sourceId: string) => {
    setDrawerLoading(true)
    try {
      const detail = await fetchAdminSourceDetail(sourceId)
      setDrawerSource(detail)
    } finally {
      setDrawerLoading(false)
    }
  }

  const columns: ColumnsType<AdminOcrSource> = [
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record) => (
        <Space>
          <Text strong>{name}</Text>
          {!record.isEnabled && <Tag color="default">disabled</Tag>}
        </Space>
      ),
    },
    {
      title: 'Type',
      dataIndex: 'sourceType',
      key: 'sourceType',
      render: (type: string) => <Tag>{type}</Tag>,
    },
    {
      title: 'Deploy',
      dataIndex: 'deploymentMode',
      key: 'deploymentMode',
      render: (mode: string | null) => mode ? <Tag color="blue">{mode}</Tag> : '-',
    },
    {
      title: 'Status',
      dataIndex: 'healthStatus',
      key: 'healthStatus',
      render: (status: string) => (
        <Tag color={statusColors[status] ?? 'default'} icon={statusIcons[status]}>
          {status}
        </Tag>
      ),
    },
    {
      title: 'Latency',
      dataIndex: 'lastResponseTimeMs',
      key: 'latency',
      render: (ms: number | null) => ms != null ? `${ms}ms` : '-',
      sorter: (a, b) => (a.lastResponseTimeMs ?? 0) - (b.lastResponseTimeMs ?? 0),
    },
    {
      title: 'Models',
      dataIndex: 'cachedModelsCount',
      key: 'models',
      render: (count: number) => count,
    },
    {
      title: 'Last Error',
      dataIndex: 'lastError',
      key: 'lastError',
      ellipsis: true,
      render: (error: string | null) =>
        error ? (
          <Tooltip title={error}>
            <Text type="danger" ellipsis style={{ maxWidth: 200 }}>{error}</Text>
          </Tooltip>
        ) : (
          <Text type="secondary">-</Text>
        ),
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_, record) => (
        <Space>
          <Tooltip title="Run healthcheck">
            <Button
              size="small"
              icon={<ReloadOutlined />}
              loading={healthcheckLoading === record.id}
              onClick={() => handleHealthcheck(record.id)}
            />
          </Tooltip>
          <Tooltip title="Details">
            <Button
              size="small"
              icon={<InfoCircleOutlined />}
              onClick={() => handleShowDetail(record.id)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>OCR Sources</Title>
        <Button icon={<ReloadOutlined />} onClick={() => loadSources()}>Refresh</Button>
      </Space>

      <Table
        columns={columns}
        dataSource={sources}
        rowKey="id"
        loading={sourcesLoading}
        pagination={false}
        size="small"
      />

      {/* Drawer с деталями */}
      <Drawer
        title={drawerSource?.name ?? 'Source Details'}
        open={!!drawerSource}
        onClose={() => setDrawerSource(null)}
        width={560}
        loading={drawerLoading}
      >
        {drawerSource && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="ID">
                <Typography.Text copyable>{drawerSource.id}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="Type">{drawerSource.sourceType}</Descriptions.Item>
              <Descriptions.Item label="Base URL">{drawerSource.baseUrl ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="Deploy Mode">{drawerSource.deploymentMode ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="Concurrency">{drawerSource.concurrencyLimit}</Descriptions.Item>
              <Descriptions.Item label="Timeout">{drawerSource.timeoutSec}s</Descriptions.Item>
              <Descriptions.Item label="Enabled">{drawerSource.isEnabled ? 'Yes' : 'No'}</Descriptions.Item>
            </Descriptions>

            <Title level={5}>Cached Models ({drawerSource.cachedModelsCount})</Title>
            <List
              size="small"
              bordered
              dataSource={drawerSource.cachedModels}
              renderItem={(model) => {
                const m = model as Record<string, unknown>
                const name = String(m.model_name ?? m.model_id ?? '')
                const hasVision = Boolean(m.supports_vision)
                return (
                  <List.Item>
                    <Text>{name}</Text>
                    {hasVision && <Tag color="blue">vision</Tag>}
                  </List.Item>
                )
              }}
              locale={{ emptyText: 'Нет кешированных моделей' }}
            />

            <Title level={5}>Recent Health Checks</Title>
            <List
              size="small"
              bordered
              dataSource={drawerSource.recentHealthChecks}
              renderItem={(check) => (
                <List.Item>
                  <Space>
                    <Tag color={statusColors[check.status] ?? 'default'}>{check.status}</Tag>
                    {check.responseTimeMs != null && <Text>{check.responseTimeMs}ms</Text>}
                    <Text type="secondary">{new Date(check.checkedAt).toLocaleString()}</Text>
                  </Space>
                </List.Item>
              )}
              locale={{ emptyText: 'Нет данных' }}
            />
          </Space>
        )}
      </Drawer>
    </div>
  )
}
