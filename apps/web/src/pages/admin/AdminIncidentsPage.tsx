/**
 * Admin Block Incidents — failed recognition attempts с контекстом.
 */

import { useEffect } from 'react'
import { Table, Tag, Space, Typography, Input, Button, Tooltip } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useAdminStore } from '../../store/useAdminStore'
import type { BlockIncident } from '../../api/adminApi'

const { Title, Text } = Typography

export default function AdminIncidentsPage() {
  const {
    incidents, incidentsMeta, incidentsLoading, incidentsFilters,
    loadIncidents,
  } = useAdminStore()

  useEffect(() => {
    loadIncidents()
  }, [loadIncidents])

  const columns: ColumnsType<BlockIncident> = [
    {
      title: 'Document',
      key: 'document',
      width: 150,
      ellipsis: true,
      render: (_, record) => record.documentTitle ?? record.documentId.slice(0, 8),
    },
    {
      title: 'Page',
      dataIndex: 'pageNumber',
      key: 'page',
      width: 60,
    },
    {
      title: 'Kind',
      dataIndex: 'blockKind',
      key: 'kind',
      width: 70,
      render: (kind: string) => <Tag>{kind}</Tag>,
    },
    {
      title: 'Source',
      dataIndex: 'sourceName',
      key: 'source',
      width: 120,
      render: (name: string | null) => name ?? '-',
    },
    {
      title: 'Model',
      dataIndex: 'modelName',
      key: 'model',
      width: 150,
      ellipsis: true,
      render: (model: string | null) => model ?? '-',
    },
    {
      title: 'Attempt',
      key: 'attempt',
      width: 80,
      render: (_, record) => `#${record.attemptNo}` + (record.fallbackNo > 0 ? ` fb${record.fallbackNo}` : ''),
    },
    {
      title: 'Error Code',
      dataIndex: 'errorCode',
      key: 'errorCode',
      width: 120,
      render: (code: string | null) =>
        code ? <Tag color="error">{code}</Tag> : <Text type="secondary">-</Text>,
    },
    {
      title: 'Error Message',
      dataIndex: 'errorMessage',
      key: 'errorMessage',
      ellipsis: true,
      render: (msg: string | null) =>
        msg ? (
          <Tooltip title={msg}>
            <Text type="danger" ellipsis style={{ maxWidth: 250 }}>{msg}</Text>
          </Tooltip>
        ) : '-',
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => <Tag color={status === 'timeout' ? 'warning' : 'error'}>{status}</Tag>,
    },
    {
      title: 'Time',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 150,
      render: (date: string) => new Date(date).toLocaleString(),
      sorter: (a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
      defaultSortOrder: 'descend',
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>Block Incidents</Title>
        <Button icon={<ReloadOutlined />} onClick={() => loadIncidents()}>Refresh</Button>
      </Space>

      {/* Фильтры */}
      <Space style={{ marginBottom: 16 }} wrap>
        <Input.Search
          placeholder="Error code"
          allowClear
          style={{ width: 180 }}
          onSearch={(val) => loadIncidents({ ...incidentsFilters, errorCode: val || undefined, offset: 0 })}
        />
        <Input.Search
          placeholder="Document ID"
          allowClear
          style={{ width: 280 }}
          onSearch={(val) => loadIncidents({ ...incidentsFilters, documentId: val || undefined, offset: 0 })}
        />
        <Input.Search
          placeholder="Source ID"
          allowClear
          style={{ width: 280 }}
          onSearch={(val) => loadIncidents({ ...incidentsFilters, sourceId: val || undefined, offset: 0 })}
        />
      </Space>

      <Table
        columns={columns}
        dataSource={incidents}
        rowKey="attemptId"
        loading={incidentsLoading}
        size="small"
        expandable={{
          expandedRowRender: (record) => (
            <Space direction="vertical" size={4} style={{ padding: '8px 16px' }}>
              <Text><strong>Attempt ID:</strong> <Typography.Text copyable>{record.attemptId}</Typography.Text></Text>
              <Text><strong>Block ID:</strong> <Typography.Text copyable>{record.blockId}</Typography.Text></Text>
              <Text><strong>Run ID:</strong> <Typography.Text copyable>{record.runId ?? '-'}</Typography.Text></Text>
              {record.errorMessage && (
                <Text><strong>Full Error:</strong> <Text type="danger">{record.errorMessage}</Text></Text>
              )}
            </Space>
          ),
        }}
        pagination={{
          total: incidentsMeta?.total ?? 0,
          pageSize: incidentsFilters.limit ?? 50,
          current: Math.floor((incidentsFilters.offset ?? 0) / (incidentsFilters.limit ?? 50)) + 1,
          onChange: (page, pageSize) => {
            loadIncidents({ ...incidentsFilters, limit: pageSize, offset: (page - 1) * pageSize })
          },
          showSizeChanger: true,
          showTotal: (total) => `${total} incidents`,
        }}
      />
    </div>
  )
}
