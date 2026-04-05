/**
 * Admin Logs/Events — system_events с фильтрами и live updates.
 */

import { useEffect, useState } from 'react'
import { Table, Tag, Space, Typography, Select, Input, Button } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useSearchParams } from 'react-router-dom'
import { useAdminStore } from '../../store/useAdminStore'
import { useAdminSSE } from '../../hooks/useAdminSSE'
import type { SystemEvent } from '../../api/adminApi'

const { Title, Text } = Typography

const severityColors: Record<string, string> = {
  debug: 'default',
  info: 'blue',
  warning: 'gold',
  error: 'red',
  critical: 'magenta',
}

function PayloadView({ payload }: { payload: Record<string, unknown> }) {
  if (!payload || Object.keys(payload).length === 0) {
    return <Text type="secondary">-</Text>
  }
  return (
    <pre style={{
      fontSize: 11,
      background: '#f5f5f5',
      padding: 8,
      borderRadius: 4,
      maxHeight: 200,
      overflow: 'auto',
      margin: 0,
    }}>
      {JSON.stringify(payload, null, 2)}
    </pre>
  )
}

export default function AdminEventsPage() {
  const {
    events, eventsMeta, eventsLoading, eventsFilters,
    loadEvents, prependEventFromSSE,
  } = useAdminStore()

  const [searchParams] = useSearchParams()
  const [initialized, setInitialized] = useState(false)

  // Инициализация фильтров из URL query params (deep-link)
  useEffect(() => {
    const filters = { ...eventsFilters }
    const runId = searchParams.get('run_id')
    const documentId = searchParams.get('document_id')
    const blockId = searchParams.get('block_id')
    if (runId) filters.runId = runId
    if (documentId) filters.documentId = documentId
    if (blockId) filters.blockId = blockId
    loadEvents(filters)
    setInitialized(true)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // SSE для live events
  useAdminSSE({
    onEvents: prependEventFromSSE,
  }, initialized)

  const columns: ColumnsType<SystemEvent> = [
    {
      title: 'Time',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 160,
      render: (date: string) => new Date(date).toLocaleString(),
      sorter: (a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
      defaultSortOrder: 'descend',
    },
    {
      title: 'Severity',
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      render: (severity: string) => <Tag color={severityColors[severity] ?? 'default'}>{severity}</Tag>,
      filters: [
        { text: 'debug', value: 'debug' },
        { text: 'info', value: 'info' },
        { text: 'warning', value: 'warning' },
        { text: 'error', value: 'error' },
        { text: 'critical', value: 'critical' },
      ],
      onFilter: (value, record) => record.severity === value,
    },
    {
      title: 'Event Type',
      dataIndex: 'eventType',
      key: 'eventType',
      width: 180,
      render: (type: string) => <Text code>{type}</Text>,
    },
    {
      title: 'Service',
      dataIndex: 'sourceService',
      key: 'sourceService',
      width: 120,
      render: (service: string | null) => service ?? '-',
    },
    {
      title: 'Payload',
      dataIndex: 'payloadJson',
      key: 'payload',
      ellipsis: true,
      render: (payload: Record<string, unknown>) => {
        const keys = Object.keys(payload)
        if (keys.length === 0) return <Text type="secondary">-</Text>
        const summary = keys.slice(0, 3).join(', ')
        return <Text type="secondary">{summary}{keys.length > 3 ? '...' : ''}</Text>
      },
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>Logs / Events</Title>
        <Button icon={<ReloadOutlined />} onClick={() => loadEvents()}>Refresh</Button>
      </Space>

      {/* Фильтры */}
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          placeholder="Severity"
          allowClear
          style={{ width: 140 }}
          value={eventsFilters.severity ?? undefined}
          onChange={(val) => loadEvents({ ...eventsFilters, severity: val ?? undefined, offset: 0 })}
          options={[
            { value: 'debug', label: 'debug' },
            { value: 'info', label: 'info' },
            { value: 'warning', label: 'warning' },
            { value: 'error', label: 'error' },
            { value: 'critical', label: 'critical' },
          ]}
        />
        <Input.Search
          placeholder="Service"
          allowClear
          style={{ width: 160 }}
          onSearch={(val) => loadEvents({ ...eventsFilters, sourceService: val || undefined, offset: 0 })}
        />
        <Input.Search
          placeholder="Event type"
          allowClear
          style={{ width: 160 }}
          onSearch={(val) => loadEvents({ ...eventsFilters, eventType: val || undefined, offset: 0 })}
        />
        <Input.Search
          placeholder="Run ID"
          allowClear
          style={{ width: 280 }}
          defaultValue={eventsFilters.runId}
          onSearch={(val) => loadEvents({ ...eventsFilters, runId: val || undefined, offset: 0 })}
        />
        <Input.Search
          placeholder="Document ID"
          allowClear
          style={{ width: 280 }}
          defaultValue={eventsFilters.documentId}
          onSearch={(val) => loadEvents({ ...eventsFilters, documentId: val || undefined, offset: 0 })}
        />
        <Input.Search
          placeholder="Block ID"
          allowClear
          style={{ width: 280 }}
          defaultValue={eventsFilters.blockId}
          onSearch={(val) => loadEvents({ ...eventsFilters, blockId: val || undefined, offset: 0 })}
        />
      </Space>

      <Table
        columns={columns}
        dataSource={events}
        rowKey="id"
        loading={eventsLoading}
        size="small"
        expandable={{
          expandedRowRender: (record) => <PayloadView payload={record.payloadJson} />,
        }}
        pagination={{
          total: eventsMeta?.total ?? 0,
          pageSize: eventsFilters.limit ?? 50,
          current: Math.floor((eventsFilters.offset ?? 0) / (eventsFilters.limit ?? 50)) + 1,
          onChange: (page, pageSize) => {
            loadEvents({ ...eventsFilters, limit: pageSize, offset: (page - 1) * pageSize })
          },
          showSizeChanger: true,
          showTotal: (total) => `${total} events`,
        }}
      />
    </div>
  )
}
