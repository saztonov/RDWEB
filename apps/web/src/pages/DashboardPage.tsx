import { Typography, Card, Row, Col } from 'antd'

const { Title, Paragraph } = Typography

export default function DashboardPage() {
  return (
    <div>
      <Title level={4}>Dashboard</Title>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={8}>
          <Card title="Documents">
            <Paragraph type="secondary">TODO: список документов</Paragraph>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={8}>
          <Card title="Recognition">
            <Paragraph type="secondary">TODO: статус распознавания</Paragraph>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={8}>
          <Card title="System Health">
            <Paragraph type="secondary">TODO: health панель</Paragraph>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
