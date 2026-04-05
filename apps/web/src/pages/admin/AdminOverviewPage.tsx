/**
 * Admin Overview — dashboard с health карточками, очередью и воркерами.
 */

import { useEffect } from 'react'
import { Card, Col, Row, Spin, Tag, Typography, Space, Statistic, Badge, Descriptions } from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  SyncOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  ApiOutlined,
  HddOutlined,
} from '@ant-design/icons'
import { useAdminStore } from '../../store/useAdminStore'
import { useAdminSSE } from '../../hooks/useAdminSSE'
import type { ServiceHealth } from '../../api/adminApi'

const { Title, Text } = Typography

const STATUS_CONFIG: Record<string, { color: string; icon: React.ReactNode }> = {
  healthy: { color: 'success', icon: <CheckCircleOutlined /> },
  degraded: { color: 'warning', icon: <ExclamationCircleOutlined /> },
  unavailable: { color: 'error', icon: <CloseCircleOutlined /> },
  unknown: { color: 'default', icon: <SyncOutlined spin /> },
}

function getStatusTag(status: string) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.unknown
  return <Tag color={cfg.color} icon={cfg.icon}>{status}</Tag>
}

function getServiceIcon(name: string) {
  if (name.includes('redis')) return <DatabaseOutlined />
  if (name.includes('supabase')) return <DatabaseOutlined />
  if (name.includes('r2')) return <HddOutlined />
  if (name.includes('openrouter')) return <ApiOutlined />
  if (name.includes('ocr_source')) return <CloudServerOutlined />
  return <CloudServerOutlined />
}

function groupServices(services: ServiceHealth[]) {
  const infra: ServiceHealth[] = []
  const providers: ServiceHealth[] = []

  for (const s of services) {
    if (s.serviceName.startsWith('infra:')) {
      infra.push(s)
    } else {
      providers.push(s)
    }
  }
  return { infra, providers }
}

function ServiceCard({ service }: { service: ServiceHealth }) {
  const displayName = service.serviceName.replace('infra:', '').replace('ocr_source:', '')
  const checkedAgo = service.checkedAt
    ? `${Math.round((Date.now() - new Date(service.checkedAt).getTime()) / 1000)}s ago`
    : '-'

  return (
    <Card size="small" hoverable>
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        <Space>
          {getServiceIcon(service.serviceName)}
          <Text strong>{displayName}</Text>
          {getStatusTag(service.status)}
        </Space>
        <Space split={<Text type="secondary">|</Text>}>
          {service.responseTimeMs != null && (
            <Text type="secondary">{service.responseTimeMs}ms</Text>
          )}
          <Text type="secondary">{checkedAgo}</Text>
        </Space>
      </Space>
    </Card>
  )
}

export default function AdminOverviewPage() {
  const { overview, overviewLoading, loadOverview, updateOverviewFromSSE } = useAdminStore()

  useEffect(() => {
    loadOverview()
  }, [loadOverview])

  // SSE для live updates
  useAdminSSE({
    onHealth: updateOverviewFromSSE,
    onWorkers: () => loadOverview(), // простой рефреш при heartbeat
  })

  if (overviewLoading && !overview) {
    return <Spin size="large" style={{ display: 'flex', justifyContent: 'center', marginTop: 80 }} />
  }

  if (!overview) {
    return <Text type="secondary">Нет данных</Text>
  }

  const { infra, providers } = groupServices(overview.services)
  const queue = overview.queue
  const workers = overview.workers

  return (
    <div style={{ padding: 24 }}>
      <Space align="center" style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0 }}>Overview</Title>
        <Badge
          status={overview.overall === 'healthy' ? 'success' : overview.overall === 'degraded' ? 'warning' : 'error'}
          text={overview.overall}
        />
      </Space>

      {/* Infrastructure */}
      <Title level={5}>Infrastructure</Title>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {infra.map((s) => (
          <Col xs={24} sm={12} md={8} lg={6} key={s.serviceName}>
            <ServiceCard service={s} />
          </Col>
        ))}
      </Row>

      {/* OCR Providers */}
      {providers.length > 0 && (
        <>
          <Title level={5}>OCR Providers</Title>
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            {providers.map((s) => (
              <Col xs={24} sm={12} md={8} lg={6} key={s.serviceName}>
                <ServiceCard service={s} />
              </Col>
            ))}
          </Row>
        </>
      )}

      {/* Queue + Workers */}
      <Row gutter={[16, 16]}>
        {/* Queue */}
        <Col xs={24} md={12}>
          <Card title="Queue" size="small">
            {queue ? (
              <Row gutter={16}>
                <Col span={8}>
                  <Statistic title="Size" value={queue.size >= 0 ? queue.size : '-'} />
                </Col>
                <Col span={8}>
                  <Statistic title="Max Capacity" value={queue.maxCapacity} />
                </Col>
                <Col span={8}>
                  <Statistic
                    title="Status"
                    value={queue.canAccept ? 'OK' : 'Full'}
                    valueStyle={{ color: queue.canAccept ? '#3f8600' : '#cf1322' }}
                  />
                </Col>
              </Row>
            ) : (
              <Text type="secondary">Нет данных</Text>
            )}
          </Card>
        </Col>

        {/* Workers */}
        <Col xs={24} md={12}>
          <Card title={`Workers (${workers?.activeCount ?? 0})`} size="small">
            {workers && workers.workers.length > 0 ? (
              <Descriptions column={1} size="small">
                {workers.workers.map((w) => (
                  <Descriptions.Item
                    key={w.workerName}
                    label={
                      <Space size={4}>
                        <Badge status="success" />
                        <Text code>{w.workerName}</Text>
                      </Space>
                    }
                  >
                    <Space split={<Text type="secondary">|</Text>}>
                      <Text>{w.memoryMb ?? '-'} MB</Text>
                      <Text>{w.activeTasks} tasks</Text>
                      <Text type="secondary">{w.host}</Text>
                    </Space>
                  </Descriptions.Item>
                ))}
              </Descriptions>
            ) : (
              <Text type="secondary">Нет активных worker-ов</Text>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
