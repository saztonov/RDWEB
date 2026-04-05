import { Layout, Button, theme } from 'antd'
import { LogoutOutlined } from '@ant-design/icons'
import { Outlet, useNavigate } from 'react-router-dom'
import Sidebar from '../components/Sidebar'
import { supabase } from '../lib/supabase'

const { Header, Content, Sider } = Layout

export default function MainLayout() {
  const { token: { colorBgContainer, borderRadiusLG } } = theme.useToken()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await supabase.auth.signOut()
    navigate('/login', { replace: true })
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider breakpoint="lg" collapsedWidth="0">
        <div style={{ height: 32, margin: 16, color: '#fff', fontWeight: 'bold', textAlign: 'center' }}>
          OCR Web
        </div>
        <Sidebar />
      </Sider>
      <Layout>
        <Header style={{ padding: '0 24px', background: colorBgContainer, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h3 style={{ margin: 0 }}>OCR Web MVP</h3>
          <Button icon={<LogoutOutlined />} onClick={handleLogout} type="text">
            Выйти
          </Button>
        </Header>
        <Content style={{ margin: '24px 16px', padding: 24, background: colorBgContainer, borderRadius: borderRadiusLG }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
