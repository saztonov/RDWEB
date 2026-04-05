import { Layout, theme } from 'antd'
import { Outlet } from 'react-router-dom'
import Sidebar from '../components/Sidebar'

const { Header, Content, Sider } = Layout

export default function MainLayout() {
  const { token: { colorBgContainer, borderRadiusLG } } = theme.useToken()

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider breakpoint="lg" collapsedWidth="0">
        <div style={{ height: 32, margin: 16, color: '#fff', fontWeight: 'bold', textAlign: 'center' }}>
          OCR Web
        </div>
        <Sidebar />
      </Sider>
      <Layout>
        <Header style={{ padding: '0 24px', background: colorBgContainer, display: 'flex', alignItems: 'center' }}>
          <h3 style={{ margin: 0 }}>OCR Web MVP</h3>
        </Header>
        <Content style={{ margin: '24px 16px', padding: 24, background: colorBgContainer, borderRadius: borderRadiusLG }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
