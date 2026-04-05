/**
 * Dashboard — обзорная страница: последние документы, быстрые действия, health.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Typography, Card, Row, Col, Table, Tag, Button, Statistic, Spin, Space } from 'antd'
import {
  FileTextOutlined,
  UploadOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

import { useWorkspace } from '../hooks/useWorkspace'
import { listDocuments, type DocumentListItem } from '../api/documentsApi'
import { apiFetch } from '../api/client'

const { Title } = Typography

const statusColors: Record<string, string> = {
  draft: 'default',
  uploading: 'processing',
  ready: 'success',
  processing: 'processing',
  error: 'error',
}

interface HealthOverview {
  overall: string
  services: Record<string, { status: string }>
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const { workspaceId, loading: wsLoading } = useWorkspace()
  const [documents, setDocuments] = useState<DocumentListItem[]>([])
  const [total, setTotal] = useState(0)
  const [docsLoading, setDocsLoading] = useState(false)
  const [health, setHealth] = useState<HealthOverview | null>(null)

  // Загрузить последние документы
  useEffect(() => {
    if (!workspaceId) return
    setDocsLoading(true)
    listDocuments(workspaceId, 10, 0)
      .then((r) => { setDocuments(r.documents); setTotal(r.total) })
      .catch(() => {})
      .finally(() => setDocsLoading(false))
  }, [workspaceId])

  // Загрузить health
  useEffect(() => {
    apiFetch<HealthOverview>('/admin/health')
      .then(setHealth)
      .catch(() => {})
  }, [])

  const columns: ColumnsType<DocumentListItem> = [
    {
      title: 'Название',
      dataIndex: 'title',
      key: 'title',
      render: (title: string, record) => (
        <a onClick={() => navigate(`/documents/${record.id}`)}>
          <FileTextOutlined style={{ marginRight: 8 }} />
          {title}
        </a>
      ),
    },
    {
      title: 'Статус',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => <Tag color={statusColors[status] || 'default'}>{status}</Tag>,
    },
    {
      title: 'Страниц',
      dataIndex: 'pageCount',
      key: 'pageCount',
      width: 80,
      align: 'center',
    },
    {
      title: 'Обновлён',
      dataIndex: 'updatedAt',
      key: 'updatedAt',
      width: 160,
      render: (val: string) => new Date(val).toLocaleString('ru-RU'),
    },
  ]

  if (wsLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', marginTop: 100 }}>
        <Spin size="large" />
      </div>
    )
  }

  const healthyCount = health
    ? Object.values(health.services).filter((s) => s.status === 'healthy').length
    : 0
  const totalServices = health ? Object.keys(health.services).length : 0

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Title level={4} style={{ margin: 0 }}>Dashboard</Title>
        <Space>
          <Button onClick={() => navigate('/documents')}>Все документы</Button>
          <Button type="primary" icon={<UploadOutlined />} onClick={() => navigate('/documents')}>
            Загрузить PDF
          </Button>
        </Space>
      </div>

      {/* Статистика */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic
              title="Документов"
              value={total}
              prefix={<FileTextOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic
              title="Здоровье системы"
              value={health ? `${healthyCount}/${totalServices}` : '...'}
              prefix={
                health?.overall === 'healthy'
                  ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
                  : health?.overall === 'degraded'
                    ? <ExclamationCircleOutlined style={{ color: '#faad14' }} />
                    : <ClockCircleOutlined />
              }
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card>
            <Statistic
              title="Workspace"
              value={workspaceId ? 'Активен' : 'Не выбран'}
              prefix={<CheckCircleOutlined style={{ color: workspaceId ? '#52c41a' : '#d9d9d9' }} />}
            />
          </Card>
        </Col>
      </Row>

      {/* Последние документы */}
      <Card
        title="Последние документы"
        extra={<Button type="link" onClick={() => navigate('/documents')}>Все</Button>}
      >
        <Table
          columns={columns}
          dataSource={documents}
          rowKey="id"
          loading={docsLoading}
          pagination={false}
          size="small"
        />
      </Card>
    </div>
  )
}
