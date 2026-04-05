import { Menu } from 'antd'
import { DashboardOutlined, FileSearchOutlined, SettingOutlined, HeartOutlined } from '@ant-design/icons'
import { useNavigate, useLocation } from 'react-router-dom'

export default function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()

  const items = [
    { key: '/dashboard', icon: <DashboardOutlined />, label: 'Dashboard' },
    { key: '/documents', icon: <FileSearchOutlined />, label: 'Documents' },
    { key: '/admin', icon: <HeartOutlined />, label: 'Admin / Ops' },
    { key: '/settings', icon: <SettingOutlined />, label: 'Settings' },
  ]

  return (
    <Menu
      theme="dark"
      mode="inline"
      selectedKeys={[location.pathname]}
      items={items}
      onClick={({ key }) => navigate(key)}
    />
  )
}
