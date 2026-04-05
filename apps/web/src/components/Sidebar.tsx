import { Menu } from 'antd'
import {
  DashboardOutlined,
  FileSearchOutlined,
  SettingOutlined,
  HeartOutlined,
  MessageOutlined,
  MonitorOutlined,
  CloudServerOutlined,
  PlayCircleOutlined,
  WarningOutlined,
  FileTextOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation } from 'react-router-dom'
import type { MenuProps } from 'antd'

type MenuItem = Required<MenuProps>['items'][number]

export default function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()

  const items: MenuItem[] = [
    { key: '/dashboard', icon: <DashboardOutlined />, label: 'Dashboard' },
    { key: '/documents', icon: <FileSearchOutlined />, label: 'Documents' },
    {
      key: '/admin',
      icon: <HeartOutlined />,
      label: 'Admin / Ops',
      children: [
        { key: '/admin/overview', icon: <MonitorOutlined />, label: 'Overview' },
        { key: '/admin/sources', icon: <CloudServerOutlined />, label: 'OCR Sources' },
        { key: '/admin/runs', icon: <PlayCircleOutlined />, label: 'Recognition Runs' },
        { key: '/admin/incidents', icon: <WarningOutlined />, label: 'Incidents' },
        { key: '/admin/logs', icon: <FileTextOutlined />, label: 'Logs / Events' },
        { key: '/admin/prompts', icon: <MessageOutlined />, label: 'Prompt Templates' },
      ],
    },
    { key: '/settings', icon: <SettingOutlined />, label: 'Settings' },
  ]

  // Определяем openKeys для подменю
  const openKeys = location.pathname.startsWith('/admin') ? ['/admin'] : []

  return (
    <Menu
      theme="dark"
      mode="inline"
      selectedKeys={[location.pathname]}
      defaultOpenKeys={openKeys}
      items={items}
      onClick={({ key }) => navigate(key)}
    />
  )
}
